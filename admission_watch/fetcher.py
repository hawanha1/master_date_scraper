"""
Polite page fetcher with the usual anti-bot techniques used by scrapers:

1. Real browser TLS / HTTP2 fingerprints (curl_cffi impersonation). Most bot walls look at the
   TLS handshake first, and python-requests is recognised instantly.
2. Fingerprint rotation: when a site blocks one browser profile, retry with another
   (Chrome / Edge / Safari / Firefox), each with a fresh session.
3. Consistent, locale-matched headers: the impersonation sets the browser's own User-Agent,
   sec-ch-ua and Accept headers (mixing a custom UA with another browser's TLS is a red flag);
   we only add Accept-Language for the site's country and a Google Referer.
4. Session warm-up: visit the homepage first so cookies (Cloudflare __cf_bm, consent, ...) are set
   before the deep page is requested, as a human visitor would.
5. Human-like pacing: one request at a time per website, with random pauses between requests.
6. Retry with exponential backoff + jitter on 429/503, honouring Retry-After.
7. Block-page detection (Cloudflare, Akamai, Incapsula, DataDome, captcha pages) instead of
   parsing the challenge page as content.
8. Fallbacks: cloudscraper (solves Cloudflare's JavaScript challenge), then a stealth headless
   browser (Patchright, see browser.py), then the Wayback Machine's copy if it is recent.
9. Optional proxy rotation (PROXIES in config.env).
10. Blocked-host memory: a host that still shows a challenge after all of the above is not retried
    for its other URLs in the same run.
11. robots.txt compliance (RobotsPolicy, RFC 9309) incl. Crawl-delay, checked before every request.
12. search(): free meta-search used by the search-index fallback for CAPTCHA-protected sites.
CAPTCHAs / "human verification" checks are never solved.
"""
from __future__ import annotations

import random
import re
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse

from urllib.robotparser import RobotFileParser

import cloudscraper
import requests
from curl_cffi import requests as creq

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

PROFILES = ["chrome131", "edge101", "safari17_0", "firefox133", "chrome124"]
ACCEPT_LANGUAGE = {
    "italy": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "germany": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}
BLOCK_MARKERS = (
    "just a moment", "cf-browser-verification", "cf_chl_", "challenge-platform", "attention required",
    "are you a robot", "verify you are human", "access denied", "incapsula", "datadome", "px-captcha",
    "request unsuccessful", "enable javascript and cookies", "captcha", "bot detection",
    "unusual traffic", "please wait while we verify", "ddos protection", "ci siamo quasi",
    "human verification", "un momento", "einen moment", "awswaf", "aws-waf-token",
)
MAX_BYTES = 12_000_000
BOT_NAME = "AdmissionWatch"      # the name robots.txt rules are matched against (plus "*")


class RobotsPolicy:
    """robots.txt compliance (RFC 9309), cached per host for the run.

    - 2xx: rules apply (for "*" and for BOT_NAME), including Crawl-delay
    - 4xx (no robots.txt): everything allowed
    - 5xx / network error / challenge page: treated as "disallow all" for this run, as the RFC requires
    """

    def __init__(self):
        self._cache: dict[str, tuple[RobotFileParser | None, str]] = {}
        self._lock = threading.Lock()

    def _load(self, root: str) -> tuple[RobotFileParser | None, str]:
        url = root + "robots.txt"
        for verify in (True, False):
            try:
                r = creq.get(url, impersonate="chrome131", timeout=15, verify=verify, allow_redirects=True)
                break
            except Exception as e:  # noqa: BLE001
                if verify and ("SSL" in str(e) or "certificate" in str(e).lower()):
                    continue
                return None, f"robots.txt unreachable ({type(e).__name__})"
        if 400 <= r.status_code < 500 and r.status_code != 429:
            rp = RobotFileParser()
            rp.parse([])                                  # no robots.txt: all allowed
            return rp, ""
        body = r.content[:500_000].decode("utf-8", "ignore")
        is_html = "html" in r.headers.get("content-type", "") or body.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
        if r.status_code >= 500 or r.status_code == 429 or (is_html and looks_blocked(r.status_code, r.content, "")):
            return None, f"robots.txt unreachable (http {r.status_code})"
        rp = RobotFileParser()
        rp.parse([] if is_html else body.splitlines())   # an HTML page instead of robots.txt = no rules
        return rp, ""

    def check(self, url: str) -> tuple[bool, str, float]:
        """(allowed, reason, crawl_delay_seconds)"""
        root = site_root(url)
        with self._lock:
            if root not in self._cache:
                self._cache[root] = self._load(root)
            rp, err = self._cache[root]
        if rp is None:
            return False, err, 0.0
        agent = BOT_NAME if any(BOT_NAME.lower() in str(e).lower() for e in rp.entries) else "*"
        if not rp.can_fetch(agent, url):
            return False, "disallowed by robots.txt", 0.0
        delay = rp.crawl_delay(agent) or 0
        return True, "", float(delay)


@dataclass
class Page:
    url: str
    status: str            # "ok", "blocked(403)", "http 404", "error: Timeout", ...
    method: str = ""       # which technique got the page
    content: bytes = b""
    ctype: str = ""
    final_url: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_pdf(self) -> bool:
        return "pdf" in self.ctype or self.content[:5] == b"%PDF-" or self.url.lower().endswith(".pdf")


def looks_blocked(status: int, body: bytes, ctype: str) -> bool:
    if status in (401, 403, 405, 406, 429, 503):
        return True
    if "pdf" in ctype:
        return False
    text = body[:80000].decode("utf-8", "ignore").lower()
    return len(body) < 60000 and any(m in text for m in BLOCK_MARKERS)


def site_root(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme or 'https'}://{p.netloc}/"


class Fetcher:
    """Thread-safe; requests to the same host are serialised and paced."""

    def __init__(self, country: str, proxies: list[str] | None = None, delay: tuple[float, float] = (0.6, 1.6),
                 robots: RobotsPolicy | None = None):
        self.lang = ACCEPT_LANGUAGE.get(country.lower(), "en-US,en;q=0.9")
        self.proxies = proxies or []
        self.delay = delay
        self._sessions: dict[tuple[str, str], creq.Session] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._last_hit: dict[str, float] = {}
        self._warm: set[tuple[str, str]] = set()
        self._profile: dict[str, int] = {}
        self.blocked_hosts: set[str] = set()   # hosts that showed a challenge after every technique
        self.robots = robots                   # None = robots.txt not checked (RESPECT_ROBOTS=false)
        self._crawl_delay: dict[str, float] = {}   # host -> Crawl-delay seconds from robots.txt
        self._lock = threading.Lock()
        self._cloud = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows"})

    # -- helpers -----------------------------------------------------------------
    def _host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(host, threading.Lock())

    def _pace(self, host: str):
        last = self._last_hit.get(host)
        if last is not None:
            gap = max(random.uniform(*self.delay), self._crawl_delay.get(host, 0))
            wait = gap - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.time()

    def _session(self, host: str, profile: str) -> creq.Session:
        key = (host, profile)
        if key not in self._sessions:
            kw = {"impersonate": profile}
            if self.proxies:
                proxy = random.choice(self.proxies)
                kw["proxies"] = {"http": proxy, "https": proxy}
            self._sessions[key] = creq.Session(**kw)
        return self._sessions[key]

    def _headers(self, referer: str) -> dict:
        return {"Accept-Language": self.lang, "Referer": referer}

    # -- main entry --------------------------------------------------------------
    def allowed(self, url: str) -> tuple[bool, str]:
        if self.robots is None:
            return True, ""
        ok, reason, delay = self.robots.check(url)
        if ok and delay:
            self._crawl_delay[urlparse(url).netloc.lower()] = delay
        return ok, reason

    def get(self, url: str, referer: str | None = None) -> Page:
        host = urlparse(url).netloc.lower()
        ok, reason = self.allowed(url)
        if not ok:
            return Page(url, f"skipped: {reason}")
        with self._host_lock(host):
            return self._get_locked(url, host, referer)

    def _get_locked(self, url: str, host: str, referer: str | None) -> Page:
        if host in self.blocked_hosts:       # don't repeat the whole chain for every URL of that host
            return Page(url, "blocked(host needs human verification)")
        last = Page(url, "error")
        start = self._profile.get(host, 0)
        order = [PROFILES[(start + i) % len(PROFILES)] for i in range(3)]
        for n, profile in enumerate(order):
            sess = self._session(host, profile)
            if (host, profile) not in self._warm:           # cookies first, like a real visit
                self._warm.add((host, profile))
                root = site_root(url)
                if root.rstrip("/") != url.rstrip("/"):
                    self._pace(host)
                    self._request(sess, root, "https://www.google.com/")
            for attempt in range(3):
                self._pace(host)
                page = self._request(sess, url, referer or "https://www.google.com/")
                page.method = f"browser-fingerprint:{profile}"
                if page.ok:
                    self._profile[host] = PROFILES.index(profile)
                    return page
                last = page
                if page.status.startswith("error") and attempt == 0:   # DNS hiccup / timeout: once more
                    time.sleep(2 + random.uniform(0, 2))
                    continue
                code = re.search(r"\((\d+)\)", page.status)
                if code and code.group(1) in ("429", "503") and attempt < 2:
                    time.sleep(min(getattr(page, "retry_after", 0) or (2 ** (attempt + 1)), 20)
                               + random.uniform(0, 1.5))
                    continue
                break
            if not last.status.startswith("blocked"):
                return last          # 404 / DNS error: another fingerprint won't help
        # Cloudflare JS challenge solver
        self._pace(host)
        try:
            r = self._cloud.get(url, timeout=25, headers=self._headers(referer or "https://www.google.com/"))
            body, ctype = r.content[:MAX_BYTES], r.headers.get("content-type", "")
            if not looks_blocked(r.status_code, body, ctype) and r.status_code < 400:
                return Page(url, "ok", "cloudflare-solver", body, ctype, str(r.url))
        except Exception:  # noqa: BLE001
            pass
        if last.status.startswith("blocked"):
            self.blocked_hosts.add(host)
        return last

    def _request(self, sess: creq.Session, url: str, referer: str) -> Page:
        for verify in (True, False):     # some university sites have broken certificate chains
            try:
                r = sess.get(url, headers=self._headers(referer), timeout=20, allow_redirects=True,
                             verify=verify)
            except Exception as e:  # noqa: BLE001
                msg = type(e).__name__
                if verify and ("SSL" in str(e) or "certificate" in str(e).lower()):
                    continue
                return Page(url, f"error: {msg}")
            body, ctype = r.content[:MAX_BYTES], r.headers.get("content-type", "")
            if looks_blocked(r.status_code, body, ctype):
                p = Page(url, f"blocked({r.status_code})")
                try:
                    p.retry_after = int(r.headers.get("retry-after", "0"))
                except ValueError:
                    p.retry_after = 0
                return p
            if r.status_code >= 400:
                return Page(url, f"http {r.status_code}")
            return Page(url, "ok", "", body, ctype, str(r.url))
        return Page(url, "error: SSL")


SEARCH_BACKENDS = ("auto", "yahoo", "duckduckgo", "brave", "mojeek")


def search(query: str, max_results: int = 10) -> list[dict]:
    """Free meta-search (ddgs); walks through engines until one answers."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []
    for n, backend in enumerate(SEARCH_BACKENDS):
        try:
            res = DDGS().text(query, max_results=max_results, backend=backend)
            if res:
                return res
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1 + n)
    return []


def wayback(url: str, max_age_days: int = 45) -> Page | None:
    """Recent Wayback Machine copy (raw, without the archive toolbar)."""
    try:
        r = requests.get("https://archive.org/wayback/available", params={"url": url}, timeout=20)
        snap = r.json().get("archived_snapshots", {}).get("closest")
        if not snap or not snap.get("available"):
            return None
        taken = datetime.strptime(snap["timestamp"][:8], "%Y%m%d").date()
        if (date.today() - taken).days > max_age_days:
            return None
        raw = re.sub(r"/web/(\d+)/", r"/web/\1id_/", snap["url"], count=1)
        r = creq.get(raw, impersonate="chrome131", timeout=30)
        if r.status_code < 400:
            return Page(url, "ok", f"web-archive copy of {taken}", r.content[:MAX_BYTES],
                        r.headers.get("content-type", ""), url)
    except Exception:  # noqa: BLE001
        pass
    return None
