"""
Optional last-resort fetcher: a real Chrome (Playwright/Patchright) for pages that stay blocked
or only render with JavaScript.

Install with:  .venv/bin/pip install patchright && .venv/bin/patchright install chromium
(patchright = Playwright with the automation leaks patched; plain playwright also works)
Without it the watcher still runs; those pages are just reported as blocked.

- Preferred engine: nodriver (drives Chrome over CDP without WebDriver/Playwright), headed. In tests
  it cleared the Cloudflare interstitial of all 8 Cloudflare-fronted Italian universities on its own,
  where Patchright did not. Headless nodriver does not (1 of 8), so the cron job runs under xvfb-run.
  Falls back to Patchright when nodriver is missing or no display is available.
- Uses installed Google Chrome when present (bundled Chromium otherwise), with a persistent profile
  per country in browser_state/<country>/ (git-ignored: it holds cookies).
- Runs headed when a display is available (the cron job runs under xvfb-run), headless otherwise.
- Locale + timezone match the site's country; waits for JS challenge pages to clear on their own.
- CAPTCHAs / "verify you are human" checks are never solved automatically. manual_verify() opens a
  visible window so a person can pass the check once; the session is kept in the profile and
  reused by the nightly run for as long as the site accepts it.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import shutil
import time
from pathlib import Path

from fetcher import BLOCK_MARKERS, Page

STATE_DIR = Path(__file__).resolve().parent / "browser_state"
TIMEZONE = {"italy": "Europe/Rome", "germany": "Europe/Berlin"}
LOCALE = {"italy": "it-IT", "germany": "de-DE"}
CHALLENGE_TITLES = ("just a moment", "ci siamo quasi", "human verification", "un momento", "einen moment",
                    "attention required", "access denied", "verify you are human", "security check")


def nodriver_available() -> bool:
    try:
        import nodriver  # noqa: F401
        return bool(os.environ.get("DISPLAY"))
    except ImportError:
        return False


def _api():
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        from playwright.sync_api import sync_playwright
    return sync_playwright


def available() -> bool:
    try:
        _api()
        return True
    except ImportError:
        return False


def _challenge(title: str, html: str) -> bool:
    if any(m in (title or "").lower() for m in CHALLENGE_TITLES):
        return True
    return len(html) < 40000 and any(m in html.lower() for m in BLOCK_MARKERS)


class StealthBrowser:
    """Use from ONE thread only (Playwright's sync API is not thread-safe).
    Only one process can open a profile at a time, so don't run --verify during the nightly job."""

    def __init__(self, headless: bool | None = None):
        self._pw = _api()().start()
        self._headless = (not os.environ.get("DISPLAY")) if headless is None else headless
        self._channel = "chrome" if shutil.which("google-chrome") else None
        self._contexts = {}

    def _context(self, country: str):
        c = country.lower()
        if c not in self._contexts:
            profile = STATE_DIR / c
            profile.mkdir(parents=True, exist_ok=True)
            os.chmod(STATE_DIR, 0o700)
            self._contexts[c] = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profile), channel=self._channel, headless=self._headless,
                no_viewport=True, locale=LOCALE.get(c, "en-US"), timezone_id=TIMEZONE.get(c, "Europe/Berlin"))
        return self._contexts[c]

    def _wait_for_content(self, page, seconds: float) -> bool:
        """True once the page is no longer a challenge page."""
        end = time.time() + seconds
        while True:
            try:
                if not _challenge(page.title(), page.content()):
                    return True
            except Exception:  # noqa: BLE001  (page navigating while we look)
                pass
            if time.time() >= end:
                return False
            time.sleep(1.2)

    def get(self, url: str, country: str) -> Page:
        page = self._context(country).new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and "pdf" in (resp.headers.get("content-type") or ""):
                return Page(url, "ok", "stealth-browser", resp.body(), "application/pdf", url)
            passed = self._wait_for_content(page, 15)      # let JS challenges finish on their own
            if passed:
                page.mouse.move(random.randint(100, 800), random.randint(100, 600))
                try:
                    page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:  # noqa: BLE001
                    pass
            html = page.content()
            if _challenge(page.title(), html):
                return Page(url, "blocked (human-verification / CAPTCHA page)")
            return Page(url, "ok", "stealth-browser", html.encode("utf-8"), "text/html", page.url)
        except Exception as e:  # noqa: BLE001
            return Page(url, f"error: {type(e).__name__}")
        finally:
            page.close()

    def manual_verify(self, url: str, country: str, timeout: float = 180) -> str:
        """Open url in the visible window and wait for a person to pass the check.
        Returns "OK" (no check or check passed) or "MANUAL_INTERVENTION_REQUIRED" (timed out)."""
        page = self._context(country).new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if self._wait_for_content(page, 15):
                return "OK"
            print(f"    -> complete the check in the browser window ({int(timeout)} s) ...", flush=True)
            return "OK" if self._wait_for_content(page, timeout) else "MANUAL_INTERVENTION_REQUIRED"
        except Exception as e:  # noqa: BLE001
            return f"error: {type(e).__name__}"
        finally:
            page.close()

    def close(self):
        for ctx in self._contexts.values():
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


PDF_JS = """
(async () => {
  const r = await fetch(URL, {credentials: 'include'});
  const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768));
  return JSON.stringify({status: r.status, ctype: r.headers.get('content-type') || '', b64: btoa(s)});
})()
"""


class NodriverBrowser:
    """Same get() interface as StealthBrowser, driven by nodriver. One thread only; the event loop
    is private to this object. Shares the browser_state/<country> profiles with StealthBrowser."""

    def __init__(self):
        import nodriver
        self._uc = nodriver
        self._loop = asyncio.new_event_loop()
        self._browsers = {}

    def _run(self, coro, timeout: float = 90):
        return self._loop.run_until_complete(asyncio.wait_for(coro, timeout))

    async def _browser(self, country: str):
        c = country.lower()
        if c not in self._browsers:
            profile = STATE_DIR / c
            profile.mkdir(parents=True, exist_ok=True)
            os.chmod(STATE_DIR, 0o700)
            self._browsers[c] = await self._uc.start(user_data_dir=str(profile), headless=False,
                                                    lang=LOCALE.get(c, "en-US"))
        return self._browsers[c]

    async def _title_html(self, tab) -> tuple[str, str]:
        return (await tab.evaluate("document.title") or ""), (await tab.get_content() or "")

    async def _get(self, url: str, country: str) -> Page:
        br = await self._browser(country)
        tab = await br.get(url)
        title, html = "", ""
        for _ in range(16):                           # let JS challenges finish (up to ~20 s)
            await asyncio.sleep(1.3)
            title, html = await self._title_html(tab)
            if (title or len(html) > 2000) and not _challenge(title, html):
                break
        if _challenge(title, html):
            return Page(url, "blocked (human-verification / CAPTCHA page)")
        await asyncio.sleep(random.uniform(1.0, 2.0))  # late-loading content
        title, html = await self._title_html(tab)
        return Page(url, "ok", "stealth-browser:nodriver", html.encode("utf-8"), "text/html",
                    await tab.evaluate("location.href") or url)

    async def _get_file(self, url: str, country: str) -> Page:
        """PDFs etc.: fetched from inside the page (same site, same browser session)."""
        br = await self._browser(country)
        tab = br.main_tab
        raw = await tab.evaluate(PDF_JS.replace("URL", json.dumps(url)), await_promise=True)
        d = json.loads(raw)
        body = base64.b64decode(d["b64"])
        if d["status"] >= 400:
            return Page(url, f"http {d['status']}")
        return Page(url, "ok", "stealth-browser:nodriver", body, d["ctype"], url)

    def get(self, url: str, country: str) -> Page:
        try:
            if url.lower().split("?")[0].endswith(".pdf"):
                page = self._run(self._get_file(url, country))
                if page.ok and not _challenge("", page.content[:40000].decode("utf-8", "ignore")) \
                        or page.is_pdf:
                    return page
            return self._run(self._get(url, country))
        except Exception as e:  # noqa: BLE001
            return Page(url, f"error: {type(e).__name__}")

    def close(self):
        for br in self._browsers.values():
            try:
                br.stop()
            except Exception:  # noqa: BLE001
                pass


def open_browser():
    """The best available browser engine for the nightly retry."""
    return NodriverBrowser() if nodriver_available() else StealthBrowser()
