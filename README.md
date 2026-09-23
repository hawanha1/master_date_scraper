# University Intake Date Scraper

Choose a **country** and the script looks up the intake dates of that country's universities on the web.
The university list comes from the `Schengen_29_Public_Universities_complete.xlsx` registry.
Results go into an Excel file with, for every intake:

- **Intake start date** (semester / classes begin)
- **Application opening date** (when available)
- **Application deadline** (last date to apply)

| University type | Intakes reported |
|---|---|
| One intake a year | Previous, Current, Next |
| Several intakes a year | Previous-2, Previous-1, Current, Next |

At minimum it always tries to capture the **previous** intake. If the first pass doesn't find it, a second pass
searches for last year's dates and archived (Wayback Machine) copies of the official pages.

Everything it uses is free: no API keys, no accounts, no paid services.

---

## Contents

1. [Requirements](#1-requirements)
2. [Get the project files](#2-get-the-project-files)
3. [Install Python](#3-install-python-310-or-newer)
4. [Create the virtual environment](#4-create-the-virtual-environment-venv)
5. [Activate the virtual environment](#5-activate-the-virtual-environment)
6. [Install the packages](#6-install-the-packages)
7. [Check the installation](#7-check-the-installation)
8. [Run the script](#8-run-the-script)
9. [All command options](#9-all-command-options)
10. [The output Excel file](#10-the-output-excel-file)
11. [Stopping, resuming and re-running](#11-stopping-resuming-and-re-running)
12. [Deactivate / next time](#12-deactivate--using-it-again-next-time)
13. [Troubleshooting](#13-troubleshooting)
14. [How it works](#14-how-it-works)
15. [Limitations](#15-limitations)

---

## 1. Requirements

| What | Detail |
|---|---|
| Python | **3.10 or newer** (tested on 3.10.12) |
| Internet | Needed for the whole run: it searches and downloads web pages |
| Disk | About 300 MB for the virtual environment |
| OS | Linux, macOS or Windows |
| Time | About **3 minutes per university** (see `-p` to go faster) |

## 2. Get the project files

All of these must be in the **same folder**:

```
uni_dates/
├── intake_scraper.py                              # the scraper (run this)
├── registry.py                                    # reads the country workbook
├── Schengen_29_Public_Universities_complete.xlsx  # country tabs with university names
├── requirements.txt                               # Python packages to install
└── README.md
```

Open a terminal **in that folder**. All commands below assume you are inside it:

```bash
cd /path/to/uni_dates        # e.g. cd ~/uni_dates   or on Windows: cd C:\Users\you\uni_dates
```

## 3. Install Python (3.10 or newer)

Check what you already have:

```bash
python3 --version        # Linux / macOS
py --version             # Windows
```

If it prints `Python 3.10.x` or higher, skip to step 4. Otherwise:

**Ubuntu / Debian**
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```
On Ubuntu 20.04 (which ships Python 3.8), install a newer version:
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.11 python3.11-venv
# then use "python3.11" instead of "python3" in step 4
```

**macOS** (with [Homebrew](https://brew.sh))
```bash
brew install python@3.12
```

**Windows**: download the installer from <https://www.python.org/downloads/>.
On the first screen tick **"Add python.exe to PATH"**, then click *Install Now*.

## 4. Create the virtual environment (venv)

A virtual environment keeps this project's packages separate from the rest of your system.
You create it **once**. It is the `.venv` folder inside the project.

```bash
# Linux / macOS
python3 -m venv .venv

# Windows (Command Prompt or PowerShell)
py -3 -m venv .venv
```

> On Ubuntu, an error like `ensurepip is not available` means the venv module is missing.
> Run `sudo apt install python3-venv` (or `python3.11-venv`) and try again.

## 5. Activate the virtual environment

Activate it **every time you open a new terminal** before running the script.

| System / shell | Command |
|---|---|
| Linux / macOS (bash, zsh) | `source .venv/bin/activate` |
| Linux / macOS (fish) | `source .venv/bin/activate.fish` |
| Windows, Command Prompt | `.venv\Scripts\activate.bat` |
| Windows, PowerShell | `.venv\Scripts\Activate.ps1` |

When it's active, your prompt starts with `(.venv)`:

```
(.venv) user@pc:~/uni_dates$
```

> **Windows PowerShell** may say *"running scripts is disabled on this system"*. Allow it for your user once, then activate again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

**Without activating:** you can skip activation by calling the venv's Python directly.
`.venv/bin/python intake_scraper.py` (Linux / macOS) or `.venv\Scripts\python intake_scraper.py` (Windows).

## 6. Install the packages

With the venv **active**:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs:

| Package | Used for |
|---|---|
| `ddgs` | Free web search (Bing / Yahoo / DuckDuckGo / Brave / Mojeek) |
| `curl_cffi` | Downloads pages looking like a real Chrome browser (gets past most bot checks) |
| `cloudscraper` | Second attempt for Cloudflare-protected pages |
| `requests` | Wayback Machine and university-domain lookups |
| `beautifulsoup4`, `lxml` | Reading HTML pages |
| `pypdf` | Reading PDF academic calendars |
| `langdetect` | Detecting the page language |
| `deep-translator` | Translating non-English pages to English (free Google endpoint) |
| `pandas`, `openpyxl` | Reading the registry workbook and writing the Excel output |

## 7. Check the installation

```bash
python -c "import intake_scraper, registry; print('OK')"
python intake_scraper.py --help
```

`OK` followed by the list of options means everything is installed.

## 8. Run the script

### 8.1 Interactive mode (recommended)

```bash
python intake_scraper.py
```

**Step 1: choose the country.** All 29 country tabs are listed with their number of universities:

```
Countries in registry (29):
   1. Austria (23)          2. Belgium (10)          3. Bulgaria (35)
   ...
  10. Germany (92)         11. Greece (25)          12. Hungary (22)
   ...
Select country (number or name): 10
```

You can type the number (`10`), the name (`Germany`) or the start of the name (`ger`).

**Step 2: choose the universities.** The country's list is printed:

```
Germany: 92 universities
    1. RWTH Aachen University  — University
    2. University of Augsburg  — University
    ...
Which universities? [Enter = all, or e.g. 1-5,8,12]:
```

| You type | Scrapes |
|---|---|
| *(just Enter)* | all universities of that country |
| `1-10` | numbers 1 to 10 |
| `3,7,12` | only those three |
| `1-5,20,40-45` | a mix of ranges and single numbers |

**Step 3: it runs.** It prints the estimated time and progress for each university. The result for every
university is written to `intake_dates_<Country>.xlsx` (e.g. `intake_dates_Germany.xlsx`) as soon as it's done:

```
Scraping 10 universities (~30 min). Saving to intake_dates_Germany.xlsx after each one. ...
=== RWTH Aachen University (Germany) ===
  official domain: rwth-aachen.de | local language(s): de
  ...
  -> RWTH Aachen University | Previous-2 October 2025 intake  start=...  deadline=...
  ...
[1/10 done] RWTH Aachen University saved
```

### 8.2 Non-interactive (same thing, no questions)

Useful for running on a server, in `screen` / `tmux`, or on a schedule:

```bash
python intake_scraper.py -c Germany                    # every German university
python intake_scraper.py -c Germany --only 1-10        # only numbers 1-10 of the German list
python intake_scraper.py -c France -p 3                # 3 universities at the same time
python intake_scraper.py -c Italy -o italy_run1.xlsx   # choose the output file name
```

### 8.3 Universities that are not in the registry

```bash
# one university
python intake_scraper.py -c Canada -u "University of Toronto"

# several from the same country
python intake_scraper.py -c Australia -u "Monash University" -u "University of Melbourne"

# a list from a CSV or Excel file with columns: country, university
python intake_scraper.py -i universities.csv -o intake_dates.xlsx
```

For `-i`, create the file yourself, e.g. `universities.csv`:
```
country,university
Germany,Technical University of Munich
Canada,University of Toronto
```

### 8.4 Using a different registry workbook

Any workbook with the same layout works: one tab per country, with a header row that has a
"university / institution" column.

```bash
python intake_scraper.py -r path/to/other_registry.xlsx
```

### 8.5 How long will it take?

About 3 minutes per university:

| Country | Universities | Sequential | With `-p 3` |
|---|---|---|---|
| Liechtenstein / Luxembourg / Malta | 1 | ~3 min | ~3 min |
| Belgium | 10 | ~30 min | ~10 min |
| Austria | 23 | ~70 min | ~25 min |
| France | 74 | ~3.7 h | ~1.3 h |
| Germany | 92 | ~4.6 h | ~1.5 h |

`-p 3` is a good maximum. Higher values make the free search engines rate-limit you, which lowers the quality of results.

## 9. All command options

| Option | Meaning | Default |
|---|---|---|
| *(none)* | Interactive: pick country, then universities | |
| `-c COUNTRY`, `--country` | Country tab to scrape. On its own it scrapes all of that country's universities. With `-u` it's just the country name for those universities | |
| `-u NAME`, `--university` | A single university (repeat for more) | |
| `-i FILE`, `--input` | CSV / XLSX with columns `country, university` | |
| `--only 1-10,15` | Subset of the country's list (skips the question) | all |
| `-r FILE`, `--registry` | The country workbook | `Schengen_29_Public_Universities_complete.xlsx` next to the script |
| `-o FILE`, `--output` | Output Excel file | `intake_dates_<Country>.xlsx` |
| `-p N`, `--parallel` | Universities scraped at the same time | 1 |
| `--fresh` | Ignore universities already saved in the output file and redo them | off |
| `--max-pages N` | Web pages downloaded per university per pass (more = slower, more thorough) | 25 |
| `-v`, `--verbose` | Detailed debug log | off |
| `-h`, `--help` | Show the options | |

## 10. The output Excel file

Written to the folder you run the command from. It has 4 sheets:

| Sheet | Contents |
|---|---|
| **Summary** | One row per university: institution type, official website, intake pattern, and the start date and deadline for each intake. Also a **"Previous intake captured?" YES/NO** column |
| **Intakes** | One row per intake (Previous-2 / Previous-1 / Current / Next). Columns: *Name in Registry*, *Institution Type*, *Intake*, *Intake Start Date*, *Application Opens*, *Application Deadline*, *Other Deadlines Seen*, *Confidence* (High/Medium/Low), *Status*, *Sources* (URLs) |
| **Evidence** | Every date the scraper found, what it decided the date means, its score, the source URL and the surrounding text, so you can check any value yourself |
| **Sources** | Every web page tried and what happened: `ok`, `blocked(403)`, `wayback-archive`, `skipped (page not about this university)`, whether it was translated, and so on |

Values you'll see in **Status**:

| Status | Meaning |
|---|---|
| `Found` | Start date and deadline were found |
| `Found (deadline not found)` | Start date found, no deadline |
| `Found (start date not found)` | Deadline found, start date not |
| `Found (start month inferred from intake label)` | e.g. only "Fall 2026" was stated, not an exact day |
| `Not found` | A past or current intake whose dates weren't found |
| `Not announced yet` | A future intake that isn't published yet (normal) |

A date written as `2026-09 (month only)` means the sources only gave the month.

## 11. Stopping, resuming and re-running

- **Stop at any time with `Ctrl+C`.** Every finished university is already saved.
- **Resume** by running the **same command** again. It reads the existing output file, skips the universities
  already in it, and continues with the rest:
  ```
  Resuming intake_dates_Germany.xlsx: 40 already done, 52 to go (use --fresh to redo them)
  ```
- **Redo everything** (for example a month later, for fresh dates) with `--fresh`, or give a new output name with `-o`.
- If the output file is **open in Excel** while the script saves (Windows locks it), the script warns you and retries.
  Close the file and it catches up. If it's still locked at the end, the results go to `…_backup_<time>.xlsx`.

Tip for long runs on a Linux server: start them inside `tmux` or `screen`, or with `nohup`, so they keep
running after you disconnect:
```bash
nohup .venv/bin/python intake_scraper.py -c Germany -p 3 > germany.log 2>&1 &
tail -f germany.log        # watch progress; Ctrl+C here only stops watching
```

## 12. Deactivate / using it again next time

Leave the virtual environment when you're done:
```bash
deactivate
```

Next time you only need to do this (no reinstall):
```bash
cd /path/to/uni_dates
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python intake_scraper.py
```

Update the packages occasionally, since search and bot-check behaviour changes over time:
```bash
pip install --upgrade -r requirements.txt
```

To start over with a clean environment, delete the `.venv` folder and repeat steps 4–6.

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` / `'py' is not recognized` | Python isn't installed or not on PATH. See step 3; on Windows, reinstall with "Add python.exe to PATH" ticked |
| `ensurepip is not available` when creating the venv | `sudo apt install python3-venv` (or `python3.X-venv` for your version) |
| `ModuleNotFoundError: No module named 'ddgs'` (or another package) | The venv isn't active or packages aren't installed. Activate (step 5), then `pip install -r requirements.txt` |
| `ERROR: ... requires a different Python` / ddgs won't install | Your Python is older than 3.10. Install a newer one (step 3) and recreate `.venv` |
| PowerShell: *running scripts is disabled* | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `registry workbook not found` | Run from the project folder, keep the `.xlsx` next to `intake_scraper.py`, or pass `-r path/to/file.xlsx` |
| `'X' is not a tab in the registry` | Spell the country like the tab name (e.g. `Czechia`, not `Czech Republic`). The error lists all valid tabs |
| Many searches show `-> 0 results` | Search engines are rate-limiting you. Lower `-p`, wait 15–30 minutes and resume (same command) |
| `Nothing left to do.` | All selected universities are already in the output file. Use `--fresh` or a new `-o` name |
| `cannot write ... (is it open in Excel?)` | Close the output file in Excel; the script saves again automatically |
| Lots of `blocked(403)` in the Sources sheet | Normal for some sites. The script falls back to the Wayback Machine, search snippets and third-party sites |
| A date looks wrong | Open the **Evidence** sheet, filter by the university, and read the *Context* column to see where it came from |
| `pip install` fails building `lxml` or `curl_cffi` | Upgrade pip first (`python -m pip install --upgrade pip`) so it uses pre-built wheels |

## 14. How it works

**Reading the registry.** Every tab whose header has a "university / institution" column is treated as a
country (the `README` and `Sources` tabs are ignored), and blank rows are skipped. Names are cleaned before searching:

| In the sheet | Searched as | Also recognised by |
|---|---|---|
| `… Life Sciences, Vienna (BOKU)` | `… Life Sciences, Vienna` | acronym BOKU |
| `Université des Antilles (University of the Antilles)` | `Université des Antilles` | the English name |
| `University of Osijek / Josip Juraj Strossmayer University of Osijek` | `University of Osijek` | the second name |
| `National University of Distance Education — UNED` | `National University of Distance Education` | UNED |
| `Medical University – Sofia` | `Medical University Sofia` | |
| `Europa-Universität Viadrina Frankfurt (Oder)` | `… Frankfurt Oder` (the bracket is part of the name) | |

Name matching ignores accents (Tromsø = Tromso, Łódź = Lodz). If a tab lists the same institution twice, it is scraped once
and the skipped row is printed, e.g. `Paris-Panthéon-Assas University` = `University of Paris 2 Panthéon-Assas`.

**Getting around blockers**

| Blocker | What the script does |
|---|---|
| Official site has a bot check / Cloudflare | Real-Chrome fingerprint (`curl_cffi`), then `cloudscraper`, then the Wayback Machine copy. If all fail, it uses third-party sites that republish the dates (DAAD, Shiksha, Yocket, LeverageEdu, …) |
| Page blocked but the search result isn't | Dates in search-result snippets are used too, at lower weight |
| Search engine rate-limits | Falls back through several free engines |
| Non-English sites | Also searches in the local language (Belgium: Dutch + French, Switzerland: German / French / Italian, chosen from the university's own name). Detects each page's language and translates the date lines to English |
| Dates only in PDF calendars | Read with `pypdf` |
| Calendar tables with the year only in the header (`2026 \| 2027 \| 2028`) | Each cell inherits its column's year |
| Only past dates published | Future intakes are marked "Not announced yet" and the previous intake is still reported |
| Page is about a different university | Skipped (name / acronym check) |

**Deciding the dates**

1. Every date near a keyword is classified as a **start** ("classes begin", "September 2026 intake", "lecture period"),
   a **deadline** ("apply by", "applications close") or an **open** date ("applications open", or the first half of "application period X – Y").
   Noise is filtered out: exams, holidays, fees, course enrolment, Erasmus/exchange, "last updated" dates.
2. Each date is scored: official site ×2, third-party ×1, search snippet ×0.5, plus how close the keyword is.
   The same sentence copied on several sites counts once.
3. The **intake pattern** (e.g. October + April for German universities) is learned from all years of evidence.
   A pattern × year grid is then filled with the best-supported date for each intake.
4. **Current** = the intake starting nearest to today (within about 4 months). **Previous** and **Next** are its neighbours in the grid.

## 15. Limitations

- Universities often have different deadlines per programme, degree level or applicant group (EU vs non-EU).
  The script reports the best-supported deadline and lists others under *Other Deadlines Seen*. Check the Evidence sheet when it matters.
- Free search engines return slightly different results on each run, so a borderline date can appear or disappear between runs.
- Pages whose content only appears after JavaScript runs aren't executed. The script relies on other sources for those.
- Very small or specialised institutions (arts academies, military schools) often publish little online. Expect more
  "Not found" results for them.
