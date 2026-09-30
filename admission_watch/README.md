# Admission Watch

A nightly job that opens the **official admissions pages** of every Italian and German public
university in your two sheets. It checks whether **today falls inside an application window**,
then emails you the result with Gmail.

- `italy_universities.xlsx`: 70 Italian universities
- `germany_universities.xlsx`: 92 German universities

Each run takes about 11 minutes for all 162 universities.

## What you get by email

Each night at 00:00 you get one email. It is only sent if something was found, unless you turn on `SEND_WHEN_EMPTY`. It contains:

- the list of universities with an open admission, written in the email text
- `open_admissions_<date>.xlsx`: university, match type, opens, closes, days left, the page text the
  dates came from, and the page link
- `scrape_problems_<date>.xlsx`: universities that couldn't be checked, with the reason

Both sheets are created in a temporary folder and **deleted right after the email is sent**, even if sending fails. No report files stay on the server.

Match types:

| Match | Meaning |
|---|---|
| `OPEN NOW` | The page gives an opening and a closing date, and today is between them |
| `Deadline coming (opening date not stated)` | Only a deadline is given, and it's within `DEADLINE_DAYS` (30) |
| `Opened recently (closing date not stated)` | Only an opening date is given, within the last `OPENED_DAYS` (45) |

Problem types: `Blocked by bot protection`, `Could not load official pages`, and `No admission dates found on official pages`.
For the last one, put a more specific page in the sheet's *Admissions Page* column.

## The two sheets

| Column | What it's for |
|---|---|
| University, Official Website | Filled in for you |
| Admissions Page | The page checking starts from. You can edit it, and put several links separated by spaces |
| **Status** | Set it to **`Applied`** (or `Skip`) and that university is no longer checked or reported. Leave it empty to keep checking |
| Notes | Your own notes. The builder also notes where it couldn't find a page |

You can edit the sheets at any time, including while the job is scheduled. They are only read, never written.

## Setup (one time)

```bash
cd /home/aslase/uni_dates/admission_watch
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/patchright install chromium          # browser fallback (about 150 MB)
sudo apt install xvfb                          # virtual screen: the browser fallback must run headed
```

**Gmail app password.** Gmail doesn't accept your normal password from scripts:

1. Go to <https://myaccount.google.com/security> and turn on **2-Step Verification**
2. Open <https://myaccount.google.com/apppasswords>, create one (name it e.g. "Admission Watch") and copy the 16 characters
3. Create your config and fill in the address, the app password and the recipient:
   ```bash
   cp config.env.example config.env
   nano config.env
   ```
4. Test it:
   ```bash
   .venv/bin/python admission_watch.py --test-email
   ```

**Cron.** The job is already installed and runs every night at 00:00 Pakistan time (the server's timezone):
```bash
crontab -l                 # see it
./install_cron.sh          # install again / repair
./install_cron.sh --remove # remove it
```
The cron line uses `flock`, so two runs can never overlap. Output goes to `logs/cron.log`, and each run also writes
`logs/run_<date>.log`. Logs older than 14 days are deleted automatically.

## Manual runs

Always start manual runs with `xvfb-run -a`. It gives the browser a virtual screen. Without it the browser
fallback can't run headed, and the Cloudflare sites come back as "Blocked by bot protection" again.

```bash
cd /home/aslase/uni_dates/admission_watch
xvfb-run -a .venv/bin/python admission_watch.py                     # a real run: checks everything and sends the email
xvfb-run -a .venv/bin/python admission_watch.py --dry-run           # check everything, print the email, send nothing
xvfb-run -a .venv/bin/python admission_watch.py --dry-run --keep    # also keep the two sheets in ./reports to look at
xvfb-run -a .venv/bin/python admission_watch.py --only "Pisa,RWTH"  # just some universities
xvfb-run -a .venv/bin/python admission_watch.py --country Italy     # one country
```

A full run takes about 25–35 minutes. The blocked sites go through the browser one at a time, about a minute each.
Don't start a manual run while the midnight job is running. The lock stops a second cron run, but a manual run
would fight over the same Chrome profile.

### What to expect in the problems sheet

In the 30 Sep 2026 test, only **IUSS Pavia** was still blocked by bot protection. It shows as
*"Main site needs human verification; no dates in search index / subdomains"*. The other entries in `scrape_problems`
are not bot blocks. They're *"No admission dates found on official pages"* (fix it by putting a more specific
Admissions Page in the sheet) or *"Not checked: site's robots.txt does not allow it"*.

Universities change their bot protection over time. If more than one or two start showing "Blocked by bot protection",
check `logs/run_<date>.log` for the line `browser engine: NodriverBrowser`. If it says `StealthBrowser` instead, the run
didn't have a screen (no `xvfb-run`) or nodriver isn't installed (`.venv/bin/pip install -r requirements.txt`).

To rebuild the sheets from the registry (keeps your Status, Notes and edited links):
```bash
.venv/bin/python build_sheets.py
```

## How it gets past bot checks

Implemented in `fetcher.py` and `browser.py`:

1. **Real browser TLS/HTTP2 fingerprint** (`curl_cffi`). Plain Python requests are recognised from the TLS handshake alone.
2. **Fingerprint rotation**. On a block it retries as Chrome, Edge, Safari or Firefox, each with a fresh session.
3. **Consistent headers**. It uses the browser's own User-Agent and client hints, plus an Accept-Language for the site's country (`it-IT` / `de-DE`) and a Google Referer.
4. **Cookie warm-up**. It visits the homepage before the deep page, like a person arriving from Google.
5. **Human pacing**. It makes one request at a time per site, with random 0.6–1.6 s pauses. Different sites are checked in parallel.
6. **Backoff**. On 429/503 it waits and retries, respecting `Retry-After`. DNS and timeout errors are retried once.
7. **Challenge detection**. It recognises Cloudflare, AWS WAF, Incapsula, DataDome and captcha pages, including the Italian and German versions ("Ci siamo quasi…").
8. **Cloudflare JS-challenge solver** (`cloudscraper`).
9. **Real Chrome browser** (`nodriver`, headed on a virtual screen via `xvfb-run`; Patchright if nodriver or a screen is missing). It uses installed Google Chrome with a saved profile per country in `browser_state/`, and locale and timezone matching the site. All pages of a blocked site, including PDFs, are then read through it. It's only used for sites still blocked after steps 1–8. Headless mode does not get past Cloudflare here (1 of 8 sites in testing), headed does (8 of 8).
10. **Recent Web Archive copy** (up to 45 days old) as a last source.
11. **Proxy rotation**, optional: add `PROXIES=` in `config.env`.
12. **Blocked-host memory**. Once a host shows a CAPTCHA, its other URLs skip the retry chain.
13. **Search-index fallback** for CAPTCHA-protected sites. It reads the university's own pages from the search engine's index of its official domain, and opens official subdomains that aren't behind the challenge. The *Read via* column in the report shows when this was used.

**Protected sites (tested 30 Sep 2026):** 20 Italian universities are behind a bot wall.
The 13 behind Cloudflare's "Just a moment…" / "Ci siamo quasi…" page (Bergamo, Brescia, Firenze, Milano, Milano-Bicocca,
Pavia, Torino, Trento, Chieti-Pescara, Foggia, Insubria, Siena, Reggio Calabria) clear it on their own in the headed browser.
The 7 behind an AWS WAF image CAPTCHA (Cagliari, Messina, Modena-Reggio, L'Orientale, Sassari, Trieste, IUSS Pavia) don't,
and the script doesn't solve CAPTCHAs. Those go through item 13, which covers 6 of the 7. IUSS Pavia still shows up in `scrape_problems`.

**Passing a check yourself:** `--verify` opens each university's page in a visible Chrome, using the same saved profile
as the nightly run. You tick the box or solve the CAPTCHA yourself, and the session stays in `browser_state/`:
```bash
.venv/bin/python admission_watch.py --verify --only "Studi Superiori di Pavia"   # needs a desktop session (or ssh -X)
```
The nightly run reuses that session only as long as the site accepts it. AWS WAF CAPTCHA tokens usually expire within minutes,
so this mostly helps for manual runs. Don't run `--verify` while the nightly job is running, because Chrome locks the profile.

## Legal / polite scraping rules (compliance layer)

These are always on (`RESPECT_ROBOTS=true` in `config.env`):

| Rule | How it's enforced |
|---|---|
| Obey **robots.txt** (RFC 9309) | Every URL is checked before it's requested, including by the stealth browser. Rules for `*` (or `AdmissionWatch`) apply. A missing robots.txt (4xx) means allowed. A robots.txt that is unreachable (5xx, timeout) means **not crawled** that night, as the RFC requires |
| Obey **Crawl-delay** | The site's delay replaces the normal 0.6–1.6 s pause (e.g. 10 s for Sapienza/Catania, 30 s for UdK Berlin) |
| One request at a time per site | A per-host lock, plus human-like pauses |
| Back off when asked | 429/503 plus `Retry-After` are respected |
| Public pages only | No logins, forms, accounts or paywalls. Only admission pages that anyone can open |
| No CAPTCHA solving | "Human verification" pages are never solved. Those sites are read through the search engine's public index instead |
| Official sources only | Only the university's own domain (plus the Web Archive / search-index copies of it) |
| No personal data | Only dates and page text about admissions are kept. Nothing is stored after the email |
| Low volume | One run per night, at most 12 pages per university |

Universities whose robots.txt forbids crawling (currently Kiel, Konstanz, Flensburg's portal) appear in
`scrape_problems` as *"Not checked: site's robots.txt does not allow it"*. Check those by hand.

Not legal advice: terms of use differ per site. The rules above are the standard good-practice baseline.

## Files

| File | Purpose |
|---|---|
| `admission_watch.py` | The nightly job |
| `fetcher.py` | Anti-bot HTTP fetching |
| `browser.py` | Browser fallback (nodriver / Patchright) and the `--verify` window |
| `windows.py` | Finds application windows in Italian, German and English text (`dal 15 luglio al 31 ottobre 2026`, `Bewerbungszeitraum 01.06.–15.07.2026`, `Bewerbungsfrist WS 2026/27: 15. Juli`, …) and ignores exam, lecture, fee, graduation, Erasmus and event dates |
| `build_sheets.py` | Builds and refreshes the two sheets from `../Schengen_29_Public_Universities_complete.xlsx` |
| `install_cron.sh` | Installs or removes the midnight cron job |
| `config.env.example` | Settings template. Copy it to `config.env`, which is private and in `.gitignore` |
