# Admission Watch: plan

This file is the working plan for the admission watcher. It records what was asked, what was built,
the decisions made, and what is still open.

**How to use it:** add your changes under [Change requests](#8-change-requests) (or edit any section
directly). Each item gets a status:

- `[x]` done
- `[ ]` to do
- `[~]` partly done / has a known limit
- `[?]` needs a decision from you

Last updated: 2026-09-30 (R12 completed)

---

## 1. Goal

A fast, simple nightly job that:

1. Opens the **official websites only** of Italian and German public universities.
2. Checks whether **today's date falls inside an open admission / application window**.
3. Emails the result (free Gmail), with the report sheets attached.
4. Deletes the report sheets after sending, so no extra files stay on the server.
5. Skips universities you have already applied to (`Status = Applied`).
6. Reports universities that could not be checked (blocked, errors, no dates found) in a separate sheet.

## 2. Requirements (as asked) and status

| # | Requirement | Status | Where |
|---|---|---|---|
| R1 | Separate folder for this task | [x] | `/home/aslase/uni_dates/admission_watch/` |
| R2 | Two separate Excel files (not one file with two tabs) | [x] | `italy_universities.xlsx`, `germany_universities.xlsx` |
| R3 | Sheet 1: all Italian public universities + official web page | [x] | 70 universities (from the Schengen registry) |
| R4 | Sheet 2: all German public universities + official web page | [x] | 92 universities (from the Schengen registry) |
| R5 | `Status` column; `Applied` = not included in notifications | [x] | Column F. `Applied` or `Skip` = not checked |
| R6 | Cron job at midnight (12 AM) | [x] | Installed in crontab, `0 0 * * *`, Asia/Karachi time |
| R7 | Check each official site: is today inside the admission window? | [x] | `admission_watch.py` + `windows.py` |
| R8 | Create a sheet of matching universities, email it, then delete it | [x] | `open_admissions_<date>.xlsx`, deleted after sending |
| R9 | Free email notification (Gmail) | [x] | Gmail SMTP + app password. Test email sent 2026-09-30 |
| R10 | Sheet of universities with scraping problems, email it, then delete it | [x] | `scrape_problems_<date>.xlsx`, same email, deleted after |
| R11 | Fast: only official sites from the sheet | [x] | About 11 min for all 162 universities (4 min direct + 7 min fallbacks for protected sites) |
| R12 | Anti-bot techniques used by scrapers | [x] | 13 techniques (section 5). 19 of 20 CAPTCHA-protected universities are now checked through their official search index / subdomains. CAPTCHA solving itself is deliberately not done |

## 3. What was built

### 3.1 Files

| File | Purpose |
|---|---|
| `admission_watch.py` | The nightly job: reads sheets, checks sites, builds report sheets, emails, deletes |
| `fetcher.py` | Anti-bot HTTP fetching (fingerprints, pacing, retries, fallbacks) |
| `browser.py` | Stealth headless browser fallback (Patchright) |
| `windows.py` | Finds application windows in Italian, German and English page text |
| `build_sheets.py` | Builds / refreshes the two university sheets (keeps your Status, Notes, edited links) |
| `install_cron.sh` | Installs or removes the midnight cron job |
| `config.env.example` | Settings template. Copy it to `config.env` (private, in `.gitignore`) |
| `requirements.txt` | Python packages for this folder's own `.venv` |
| `README.md` | Setup and usage instructions |
| `PLAN.md` | This file |

### 3.2 Sheet columns

`#` · `Country` · `University` · `Official Website` · `Admissions Page` · `Status` · `Notes`

- **Admissions Page:** where checking starts. Several links can be added, separated by spaces.
  - Found automatically for 44/70 Italian and 87/92 German universities.
  - The rest start from the homepage.
- **Status:** empty means checked every night. `Applied` or `Skip` means ignored.
- The sheets are only read by the job, never written. You can edit them any time.

### 3.3 Nightly flow

1. **00:00:** cron starts the job (`flock` prevents two runs overlapping).
2. **Read sheets:** load both sheets and drop rows with `Status = Applied / Skip`.
3. **Crawl:** for each university, in parallel (12 at a time):
   1. Open the *Admissions Page* (or the homepage).
   2. Follow up to 12 admission-related links on the same website (deadlines, calendars, calls, PDFs).
   3. Skip pages that are not about admission (news, events, Erasmus, PhD, graduation, jobs, competitions, funding).
4. **Find windows:** search the page text for application windows (section 4).
5. **Browser retry:** blocked sites get one retry in the stealth browser.
6. **Build reports:** create the two report sheets in a temporary folder.
7. **Email:** one email with the summary in the text and the sheets attached.
8. **Delete:** remove the temporary folder, even if the email failed.
9. **Log:** write `logs/run_<date>.log` and `logs/cron.log`. Logs older than 14 days are deleted.

## 4. Date matching rules

- **What counts as an admission window:**
  - a date or date range near admission words, for example *immatricolazioni, ammissione, bando, preiscrizione, Bewerbung, Zulassung, Einschreibung, application, admission*
  - and **not** closer to exclusion words, for example *esami, lezioni, Prüfung, Vorlesung, tasse, laurea sessions, Erasmus, borse, events, published/updated*
- **Recognised date formats:**
  - `15 luglio 2026`, `15. Juli 2026`, `July 15, 2026`
  - `15.07.2026`, `15/07/2026`, `2026-07-15`
  - `dal 15 luglio al 31 ottobre 2026`, `01.06.–15.07.2026`
- **Missing years** are taken from the academic year on the page (`Wintersemester 2026/27`, `a.a. 2026/2027`).
- **Match types reported:**

| Match | Rule |
|---|---|
| `OPEN NOW` | opening date ≤ today ≤ closing date |
| `Deadline coming (opening date not stated)` | only a deadline, and it's within `DEADLINE_DAYS` (default 30) |
| `Opened recently (closing date not stated)` | only an opening date, within the last `OPENED_DAYS` (default 45) |

- **Not reported:** windows that open in the future ("opens soon") were removed on purpose, because the requirement is "today inside the window".

## 5. Anti-bot techniques (implemented)

1. [x] Real browser TLS/HTTP2 fingerprints (`curl_cffi`)
2. [x] Fingerprint rotation on block: Chrome → Edge → Safari → Firefox, each with a fresh session
3. [x] Consistent browser headers, plus a locale-matched `Accept-Language` (`it-IT` / `de-DE`) and a Google Referer
4. [x] Cookie warm-up: visit the homepage before the deep page
5. [x] Human pacing: one request at a time per site, with random 0.6–1.6 s pauses
6. [x] Backoff on 429/503 with `Retry-After`. DNS and timeout errors are retried once
7. [x] Block-page detection: Cloudflare, AWS WAF, Incapsula, DataDome, captcha pages, and the Italian/German challenge pages
8. [x] Cloudflare JS-challenge solver (`cloudscraper`)
9. [x] Stealth headless browser (Patchright) with locale and timezone matching the site. It stops after 3 CAPTCHA pages in a row, to stay fast
10. [x] Recent Web Archive copy (≤ 45 days old) as a last source
11. [x] Optional proxy rotation (`PROXIES=` in `config.env`)
12. [x] Blocked-host memory: once a host shows a CAPTCHA, its other URLs skip the retry chain (keeps the run fast)
13. [x] **Search-index fallback** for CAPTCHA-protected sites:
    - reads the university's own pages from the search engine's index of its official domain (`site:unimi.it immatricolazioni 2026/2027`)
    - also opens official subdomains that are not behind the challenge (e.g. `web.unica.it`, `sec.unich.it`)
    - the report's *Read via* column says when a result came this way, so it can be checked on the page
14. [x] **Not done, on purpose:** solving CAPTCHAs or Cloudflare "human verification" checkboxes. That check is the site's explicit "no automated access" signal, and getting past it would mean defeating an access control, not scraping better. Item 13 covers those universities instead

## 5b. Legal / polite scraping (compliance layer)

- [x] robots.txt compliance (RFC 9309) on every request, including the stealth browser. Unreachable robots.txt means not crawled
- [x] Crawl-delay honoured (Sapienza, Catania, Teramo, Marche: 10 s; UdK Berlin: 30 s; Augsburg, Bonn, Folkwang: 1 s; HFBK: 5 s)
- [x] One request at a time per site, human pauses, Retry-After respected
- [x] Public pages only; no logins, forms or CAPTCHA solving
- [x] Official domains only. LMU was pointing at a third-party site (mygermanuniversity.com); fixed to lmu.de
- [x] No personal data kept; report files deleted after the email
- [x] Robots-disallowed universities reported as a separate problem: Kiel, Konstanz, Flensburg (portal)
- [?] Honest User-Agent: requests currently look like a normal browser (needed to get past bot walls). A strict mode could send `AdmissionWatch/1.0 (+your email)` instead, but many sites would then block it. Decide if you want that as an option

## 6. Test results (dry run, 2026-09-30, all 162 universities)

**After the R12 work (latest):**

- **Run time:** about 11 minutes.
- **Matches:** 75 universities (was 49). 18 of them were read via the search index / subdomains, e.g. Milano, Firenze, Torino, Siena, Pavia, Trento, Cagliari, Bergamo, Insubria.
- **Problems:** 52 (was 77)
  - `No admission dates found on official pages`: 50 (35 Germany, 15 Italy)
  - `Could not load official pages`: 1
  - still blocked with nothing indexed: 1 (IUSS Pavia)

**Before the R12 work:**

- **Run time:** about 4 minutes.
- **Matches:** 49 universities, 34 of them `OPEN NOW`, for example:
  - TU Berlin (01.09 – 01.10)
  - Freiburg, Bayreuth, RWTH
  - Pisa, Catania, Bari, Politecnico di Bari, Salerno, Ferrara
- **Problems:** 77
  - `No admission dates found on official pages`: 57 (41 Germany, 16 Italy)
  - `Blocked by bot protection`: 19 (all Italy, Cloudflare human verification)
  - `Could not load official pages`: 1
- **Fixes made during testing:**
  - 6 wrong websites corrected: Chieti-Pescara, Foreigners Siena, Politecnico Torino, GSSI, Konstanz, BTU Cottbus
  - 15 wrong start pages (news / PhD / careers pages) replaced
  - filters added for event, news, Erasmus, graduation-exam, funding and doctoral pages
- **Not re-tested yet:** after the last filter change and the 15 start-page fixes, only 8 universities were re-checked, not all 162.

## 7. Open items / known limits

| # | Item | Status | Proposed next step |
|---|---|---|---|
| O1 | Gmail sending | [x] | Test email sent successfully on 2026-09-30 |
| O2 | CAPTCHA-protected Italian sites | [x] | 19 of 20 now checked through the search index / subdomains. Only IUSS Pavia is left: check it by hand, or put a non-protected page in *Admissions Page* |
| O3 | 57 universities: no dates found on the pages reached | [ ] | Put a more specific deadlines page in *Admissions Page* (e.g. "Termine und Fristen", "Scadenze immatricolazioni") |
| O4 | 26 Italian + 5 German rows have no *Admissions Page* | [ ] | Fill in by hand, or improve `build_sheets.py` link discovery |
| O5 | One university can have many programmes with different deadlines; the report lists up to 6 windows per university | [?] | Decide: keep all, or only the earliest-closing one |
| O6 | "Deadline coming" and "Opened recently" are included, not only `OPEN NOW` | [?] | Decide: keep them, or only send `OPEN NOW` |
| O7 | Full 162-university dry run after the latest fixes | [ ] | Run `.venv/bin/python admission_watch.py --dry-run --keep` and review |
| O8 | Email sent only when there are matches or problems (`SEND_WHEN_EMPTY=false`) | [?] | Decide: also send an "all quiet" email? |

## 8. Change requests

Add new requests here. One line each is enough; I will turn them into tasks.

| # | Request | Priority | Status | Notes |
|---|---|---|---|---|
| C1 | Implement proper legal web scraping (robots.txt, crawl-delay, official-only) | High | [x] | Done 2026-09-30, see 5b |
| C2 |  |  | [ ] |  |
| C3 |  |  | [ ] |  |

## 9. How to run / check

```bash
cd /home/aslase/uni_dates/admission_watch
.venv/bin/python admission_watch.py --dry-run --keep    # full check, no email, keep sheets in ./reports
.venv/bin/python admission_watch.py --only "Pisa,RWTH"  # just some universities
.venv/bin/python admission_watch.py --test-email        # test Gmail
.venv/bin/python build_sheets.py                        # rebuild sheets (keeps Status / Notes / links)
crontab -l                                              # see the midnight job
./install_cron.sh --remove                              # remove the midnight job
```
