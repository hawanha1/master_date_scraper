# University application-date scraper: technical implementation prompt

## Role

Act as a senior Python web-scraping engineer.

I already have a working university application-date scraper that extracts application opening dates, closing dates, semester/intake information, and application status from official university websites.

The remaining problem is that some official university websites use JavaScript rendering, Cloudflare or similar browser challenges, rate limiting, or other anti-automation mechanisms. These mechanisms sometimes prevent my scraper from reaching the actual application-date information.

Your task is to inspect my existing implementation and extend it into a reliable, maintainable admission-date monitoring system.

### Important boundary

The objective is **not to bypass, defeat, weaken, forge, or circumvent website security mechanisms**.

Do not implement:

* CAPTCHA-solving services
* CAPTCHA/Turnstile token generation or forgery
* Cloudflare challenge bypasses
* challenge-token extraction or replay
* browser fingerprint spoofing
* TLS fingerprint spoofing
* residential-proxy rotation intended to evade blocking
* stolen or replayed cookies
* authentication bypass
* modification of challenge JavaScript
* disabling security controls
* accessing private/non-public APIs
* any technique intended to evade a university's access restrictions

Instead, use normal browser automation, legitimate browser execution, controlled crawling, human interaction when a challenge requires it, and publicly accessible information.

If a challenge requires human interaction, open the browser visibly and allow the user to complete the challenge normally. After successful access, continue the scraper and, where appropriate, preserve the legitimate browser session.

---

# 1. First inspect the existing project

Before changing anything, inspect the complete existing project.

Read:

* `STATUS.md`
* scraper source files
* configuration
* requirements/package files
* database/storage code
* university-specific adapters
* tests
* logging
* existing browser automation
* existing HTTP client
* date extraction logic
* retry logic
* concurrency logic

Determine exactly:

1. Which Python version is being used.
2. Which packages are already installed.
3. Which HTTP client is being used.
4. Which HTML parser is being used.
5. Whether Playwright/Selenium is already installed.
6. How requests are currently made.
7. How pages are currently parsed.
8. How application dates are currently extracted.
9. How dates are stored.
10. How failures are currently represented.
11. How 403/429/503 responses are handled.
12. Whether JavaScript-rendered pages are supported.
13. Whether browser sessions are already persisted.
14. Whether network/API requests are already inspected.
15. Whether university-specific scraping rules already exist.

Do not replace working code unnecessarily.

Reuse the current architecture where it is sound.

Before making major changes, explain:

* what already works;
* what is failing;
* why it is failing;
* what should be changed;
* what should remain unchanged.

---

# 2. Research current technical documentation

Before implementing the solution, research the current official documentation for the technologies involved.

At minimum research:

* Playwright Python
* Chromium
* Playwright browser contexts
* Playwright storage state
* Playwright cookies/local storage handling
* Playwright request monitoring
* Playwright response monitoring
* Playwright `expect_response`
* HTTPX
* BeautifulSoup
* lxml
* Pydantic
* Tenacity
* Python `dateutil`
* Scrapy
* Scrapy AutoThrottle
* Scrapy robots.txt handling
* Cloudflare bot detection concepts
* Cloudflare Turnstile concepts

Prefer official documentation.

Do not assume that changing a `User-Agent`, adding random headers, or using a proxy solves modern bot protection.

Modern anti-automation systems can consider JavaScript execution, browser/environment signals, request patterns, behavior, rate, and other signals.

---

# 3. Target architecture

The scraper should use this architecture:

```text
Official university URL
        |
        v
Access/policy check
        |
        v
Normal HTTP request
        |
        +--------------------+
        |                    |
        v                    v
Useful HTML             Insufficient
        |               / blocked /
        |              JS required /
        |             challenge / etc.
        |                    |
        |                    v
        |              Playwright
        |               Chromium
        |                    |
        |             JavaScript executes
        |                    |
        |          challenge detected?
        |              /          \
        |            yes           no
        |             |             |
        |      human completes      |
        |      challenge normally   |
        |             |             |
        |             +------+------+
        |                    |
        +--------------------+
                     |
                     v
             Inspect page/network
                     |
                +----+----+
                |         |
               HTML      JSON/API
                |         |
                +----+----+
                     |
                     v
              Date extraction
                     |
                     v
              Date validation
                     |
                     v
             Change detection
                     |
                     v
                Persistence
                     |
                     v
                Notification
```

The scraper should use two primary fetching modes:

### Mode 1: HTTP

Use a normal HTTP client first because it is faster and cheaper.

### Mode 2: Browser

Use Playwright when:

* JavaScript is required;
* HTML is incomplete;
* content is dynamically loaded;
* a browser challenge is presented;
* normal HTTP access receives a response that indicates browser execution is required.

---

# 4. Recommended Python packages

Evaluate the existing dependencies before installing anything.

Recommended baseline:

```bash
python -m venv .venv
source .venv/bin/activate

pip install playwright
pip install httpx
pip install beautifulsoup4
pip install lxml
pip install tenacity
pip install pydantic
pip install python-dateutil
pip install structlog

playwright install chromium
```

Package responsibilities:

| Package           | Purpose                                                   |
| ----------------- | --------------------------------------------------------- |
| `playwright`      | Real Chromium browser automation and JavaScript execution |
| `httpx`           | Normal HTTP requests                                      |
| `beautifulsoup4`  | HTML parsing                                              |
| `lxml`            | Fast HTML/XML parsing                                     |
| `tenacity`        | Retry and exponential backoff                             |
| `pydantic`        | Data validation                                           |
| `python-dateutil` | Date parsing                                              |
| `structlog`       | Structured logging                                        |

Do not install packages that are not needed.

Do not introduce Scrapy unless the existing project needs a full crawling framework.

---

# 5. Playwright browser fallback

Use Playwright Python with Chromium.

During development use:

```python
headless=False
```

so that browser behavior and challenges can be inspected.

Basic structure:

```python
from playwright.async_api import async_playwright


async def open_university(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False
        )

        context = await browser.new_context()

        page = await context.new_page()

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        print("Title:", await page.title())

        await browser.close()
```

Adapt this to the existing architecture instead of blindly replacing existing browser code.

---

# 6. Detect browser challenges

The scraper must distinguish between:

* actual university content;
* JavaScript-rendered content;
* a browser/security challenge;
* an access-denied page;
* a rate-limit page;
* a temporary server error.

Create a challenge detector.

Possible textual indicators include:

```text
checking your browser
verify you are human
just a moment
security check
enable javascript
```

Example:

```python
CHALLENGE_MARKERS = [
    "checking your browser",
    "verify you are human",
    "just a moment",
    "security check",
    "enable javascript",
]
```

The detector only identifies the challenge.

It must not solve or bypass it.

Conceptual flow:

```python
if await is_challenge_page(page):
    print("Browser challenge detected.")
    print("Complete the challenge in the browser.")

    await wait_until_real_page_is_available(page)
```

Use a reasonable timeout.

If the challenge is not completed, return a clear status such as:

```text
CHALLENGE
MANUAL_INTERVENTION_REQUIRED
```

Do not return:

```text
NOT_OPEN
```

---

# 7. Human-assisted browser challenge

When a university website presents a challenge that requires user interaction:

1. Launch Chromium visibly.
2. Navigate to the official university URL.
3. Detect the challenge.
4. Pause the scraper.
5. Allow the user to complete the challenge normally.
6. Detect when the actual university page becomes available.
7. Continue extraction.
8. Save legitimate browser state if appropriate.

Do not automatically solve the challenge.

Do not manipulate challenge tokens.

Do not attempt to imitate or forge the browser's security response.

---

# 8. Browser session persistence

Use Playwright storage state when a legitimate browser session should be reused.

Example:

```python
await context.storage_state(
    path="browser_state.json"
)
```

Later:

```python
context = await browser.new_context(
    storage_state="browser_state.json"
)
```

Store browser state securely.

Never commit it to Git.

Add something similar to:

```gitignore
browser_state/
*.state.json
```

Browser state can contain sensitive cookies/session information.

Do not store or replay another user's cookies or authentication information.

If an existing secure session-management mechanism exists, reuse it.

---

# 9. Network/API discovery

This is one of the most important parts of the implementation.

Modern university websites frequently work like:

```text
Initial HTML
      |
      v
JavaScript application
      |
      v
fetch()/XHR
      |
      v
JSON API
      |
      v
Application dates
      |
      v
Rendered UI
```

Therefore, do not assume that scraping the final DOM is always the best solution.

Use Playwright's network monitoring.

Example:

```python
page.on(
    "request",
    lambda request: print(
        "REQUEST",
        request.method,
        request.url,
    )
)

page.on(
    "response",
    lambda response: print(
        "RESPONSE",
        response.status,
        response.url,
    )
)
```

Inspect requests containing terms such as:

```text
application
applications
admission
deadline
deadlines
date
dates
semester
intake
program
study
application-period
application-periods
api
```

If the university frontend requests structured JSON containing application dates and that endpoint is publicly accessible, prefer the structured data over complicated DOM parsing.

---

# 10. Capture API responses

When the relevant endpoint is known, use Playwright response waiting.

Example:

```python
async with page.expect_response(
    "**/api/application-periods"
) as response_info:

    await page.goto(url)

response = await response_info.value

data = await response.json()
```

The endpoint above is only an example.

Do not assume a university has that exact endpoint.

Discover the actual endpoint through the browser's network activity.

If the endpoint is genuinely public and does not require bypassing an access control, determine whether it can safely be fetched with HTTPX.

Otherwise keep the request inside the legitimate browser context.

---

# 11. Do not blindly convert browser requests to HTTP requests

If Playwright discovers:

```text
GET /api/application-periods
```

do not immediately switch to:

```python
httpx.get(api_url)
```

The endpoint might depend on:

* legitimate session cookies;
* CSRF protection;
* authorization;
* origin;
* referer;
* browser state.

First determine whether the endpoint is actually public.

Do not bypass authentication or access controls.

---

# 12. HTTP response classification

Create a central response classifier.

At minimum distinguish:

```text
200  -> success / inspect content
403  -> access denied / investigate
429  -> rate limited
503  -> temporary service/challenge issue
522  -> connection/service issue
524  -> timeout/service issue
5xx  -> server-side failure
```

Example:

```python
BOT_RELATED_STATUS_CODES = {
    403,
    429,
    503,
    522,
    524,
}
```

These codes are signals, not proof of a bot challenge.

Inspect:

* response body;
* headers;
* redirects;
* page title;
* content;
* browser behavior.

A 403 could simply mean that access is forbidden.

A 429 means rate limiting and should trigger throttling.

A 503 could be temporary server failure or a challenge.

---

# 13. Rate limiting and exponential backoff

Never continuously retry a blocked website.

Use:

* exponential backoff;
* maximum retry count;
* `Retry-After` handling;
* per-domain delays;
* concurrency limits;
* request timeouts.

Example:

```python
from tenacity import retry
from tenacity import wait_exponential
from tenacity import stop_after_attempt


@retry(
    wait=wait_exponential(
        multiplier=2,
        min=5,
        max=120,
    ),
    stop=stop_after_attempt(5),
)
async def fetch_with_retry(url):
    ...
```

If the website returns `429`, slow down rather than increasing traffic.

---

# 14. Per-domain throttling

The scraper will monitor many universities.

Do not send high-volume parallel requests to every domain.

Use per-domain configuration:

```python
DOMAIN_DELAY = {
    "uni-a.de": 5,
    "uni-b.fr": 8,
    "uni-c.it": 5,
}
```

These values are examples only.

Choose delays based on:

* website behavior;
* published policies;
* response latency;
* rate-limit responses;
* reasonable crawling practices.

Use concurrency limits.

---

# 15. Scrapy

Only introduce Scrapy if the project has grown enough to benefit from a full crawler framework.

Potential benefits include:

* request scheduling;
* concurrency control;
* retries;
* robots.txt handling;
* duplicate filtering;
* caching;
* pipelines;
* throttling.

If Scrapy is used, evaluate:

```text
Scrapy
+
Playwright integration
```

Use Playwright as the browser execution layer.

Do not use Scrapy as a mechanism for defeating anti-bot systems.

---

# 16. Robots.txt and access policies

Check the university's published crawling/access rules.

Respect applicable:

* robots.txt;
* terms of use;
* rate limits;
* authentication requirements;
* access restrictions.

Do not interpret a technical vulnerability or an accidentally exposed endpoint as permission to access private information.

The scraper should only collect the public admission information required by the project.

---

# 17. Project structure

Separate the different responsibilities.

Recommended structure:

```text
university_scraper/
│
├── app.py
│
├── config/
│   ├── universities.py
│   └── settings.py
│
├── fetchers/
│   ├── http.py
│   └── browser.py
│
├── protection/
│   ├── detector.py
│   └── session.py
│
├── network/
│   └── api_discovery.py
│
├── extractors/
│   ├── html_dates.py
│   ├── json_dates.py
│   └── university_specific.py
│
├── parsers/
│   └── dates.py
│
├── models/
│   └── application_period.py
│
├── storage/
│   └── database.py
│
├── logs/
│
├── browser_state/
│
└── tests/
```

This is a target structure.

If the existing project has a good structure, adapt it rather than reorganizing everything unnecessarily.

---

# 18. Separate fetching from extraction

The architecture should conceptually separate:

```text
HTTP fetching
Browser fetching
Challenge detection
Session management
Network inspection
HTML extraction
JSON extraction
Date parsing
Date validation
University-specific rules
Persistence
Change detection
Notifications
Logging
```

Do not put bot/challenge handling directly inside university-specific date parsers.

---

# 19. Application-period data model

Create or adapt a model similar to:

```python
from datetime import date
from pydantic import BaseModel


class ApplicationPeriod(BaseModel):
    university: str
    program: str | None
    country: str
    semester: str | None

    opens: date | None
    closes: date | None

    source_url: str

    discovered_at: date
    extraction_method: str
```

Possible extraction methods:

```text
html
json_api
browser_dom
manual_review
```

Add additional fields if the existing application requires them.

---

# 20. Application status

The scraper must distinguish between actual application status and scraper failure.

Possible statuses:

```text
NOT_OPEN
OPEN
CLOSED
DATE_CHANGED
CONTENT_CHANGED
CHALLENGE
MANUAL_INTERVENTION_REQUIRED
BLOCKED
RATE_LIMITED
TEMPORARY_ERROR
PARSE_ERROR
UNKNOWN
```

Never convert technical failures into an application status.

For example:

```text
429 != NOT_OPEN
403 != NOT_OPEN
CHALLENGE != NOT_OPEN
PARSE_ERROR != NOT_OPEN
TIMEOUT != NOT_OPEN
```

If the scraper cannot determine the actual application state, return `UNKNOWN` or the appropriate technical failure state.

---

# 21. Date extraction requirements

The scraper should identify:

* application opening date;
* application closing date;
* application deadline;
* application period;
* semester;
* intake;
* academic year;
* winter semester;
* summer semester;
* rolling admission;
* program-specific deadline;
* international/non-EU deadline where explicitly stated.

Do not simply collect every date appearing on the page.

Use surrounding text and semantic context.

For example:

```text
Application deadline: 15 January 2027
```

is an application deadline.

But:

```text
Last updated: 30 September 2026
```

is not an application deadline.

And:

```text
Program starts: 1 October 2027
```

is a program-start date, not necessarily an application deadline.

---

# 22. Date normalization

Normalize dates into a consistent internal representation.

Prefer:

```text
YYYY-MM-DD
```

for stored dates.

Handle:

* `15 January 2027`
* `January 15, 2027`
* `15.01.2027`
* `15/01/2027`
* localized formats
* textual date ranges
* semester-based periods

Do not silently guess ambiguous dates.

If a date cannot be safely interpreted, mark it for review.

---

# 23. Application periods with only partial information

The scraper must support:

```text
opening date known
closing date unknown
```

and:

```text
closing date known
opening date unknown
```

For example:

```python
opens = date(...)
closes = None
```

Do not invent missing dates.

---

# 24. Rolling admissions

Support statements such as:

```text
Applications are accepted throughout the year.
```

or:

```text
Applications are accepted on a rolling basis.
```

These should not be converted into fake opening/closing dates.

Represent rolling admission explicitly.

---

# 25. Evidence capture

For every extracted application period, save enough evidence to verify the result.

Recommended fields:

```text
university
program
source URL
page title
retrieved timestamp
application opening date
application closing date
semester
extraction method
source text/snippet
API endpoint, if applicable
```

Where practical, save:

* HTML snapshot;
* screenshot;
* raw JSON response.

Do not store unnecessary personal information.

The evidence should explain why the scraper produced a specific date.

---

# 26. Change detection

Store the previous result.

Example:

```json
{
  "opens": "2026-11-01",
  "closes": "2027-01-15"
}
```

New result:

```json
{
  "opens": "2026-12-01",
  "closes": "2027-02-15"
}
```

Compare normalized values.

Generate events such as:

```text
APPLICATION_OPEN_DATE_CHANGED
APPLICATION_DEADLINE_CHANGED
APPLICATION_STATUS_CHANGED
APPLICATION_CONTENT_CHANGED
```

Do not create false alerts because of:

* whitespace;
* HTML formatting;
* irrelevant page changes;
* timestamps;
* navigation changes.

Normalize relevant content before comparing it.

---

# 27. University-specific adapters

Do not create one enormous parser containing hundreds of:

```python
if university == ...
```

conditions.

Use a common adapter interface where appropriate.

Example:

```python
class UniversityAdapter:

    async def fetch(self, url):
        ...

    async def extract_application_periods(self, page):
        ...

    def normalize(self, data):
        ...
```

Then use specialized adapters only where required:

```text
adapters/
    university_a.py
    university_b.py
    university_c.py
```

Common functionality should remain shared.

---

# 28. Failure handling

Every crawl should produce a structured result.

Success:

```python
{
    "status": "SUCCESS",
    "university": "...",
    "url": "...",
    "extraction_method": "json_api",
    "application_periods": [...]
}
```

Challenge:

```python
{
    "status": "CHALLENGE",
    "university": "...",
    "url": "..."
}
```

Manual intervention:

```python
{
    "status": "MANUAL_INTERVENTION_REQUIRED",
    "university": "...",
    "url": "..."
}
```

Rate limited:

```python
{
    "status": "RATE_LIMITED",
    "university": "...",
    "url": "..."
}
```

Parse failure:

```python
{
    "status": "PARSE_ERROR",
    "university": "...",
    "url": "..."
}
```

Do not hide failures behind:

```python
[]
```

An empty application-period list can mean:

1. there genuinely are no published dates; or
2. the scraper failed.

Those cases must be distinguishable.

---

# 29. Logging

Use structured logging.

Log at least:

```text
university
URL
HTTP status
browser used
challenge detected
challenge completed
network endpoint discovered
extraction method
dates extracted
retry count
elapsed time
final status
```

Example:

```text
university=UniversityX
status=SUCCESS
method=json_api
opens=2026-11-01
closes=2027-01-15
```

Never log:

* cookies;
* authorization headers;
* session tokens;
* passwords;
* private credentials;
* sensitive browser state.

---

# 30. Testing

Add tests for HTTP behavior:

* 200 response;
* 403 response;
* 429 response;
* 503 response;
* timeout;
* malformed HTML.

Add browser tests for:

* JavaScript-rendered page;
* challenge detection;
* successful manual challenge completion;
* challenge timeout;
* browser session restoration.

Add extraction tests for:

* normal HTML dates;
* JSON dates;
* multiple application periods;
* missing opening date;
* missing closing date;
* localized date formats;
* rolling admission;
* ambiguous dates;
* program-specific deadlines.

Add change-detection tests for:

* unchanged dates;
* changed opening date;
* changed closing date;
* newly opened application;
* newly closed application;
* irrelevant page changes.

Add failure-state tests to guarantee:

```text
429
403
challenge
timeout
parse error
```

are never incorrectly reported as:

```text
NOT_OPEN
```

---

# 31. Diagnostic classification

Before implementing any "bot-check solution", determine which situation actually exists.

## Case A: JavaScript rendering

```text
HTTP -> 200
HTML -> incomplete
Browser -> content appears
```

Solution:

```text
Playwright
```

No security bypass is required.

## Case B: Browser challenge

```text
HTTP -> 403/503/challenge HTML
Browser -> security challenge
```

Solution:

```text
Playwright
+
normal browser execution
+
human interaction if required
```

## Case C: Rate limiting

```text
200
200
200
429
```

Solution:

```text
lower request rate
per-domain throttling
Retry-After
exponential backoff
```

## Case D: Public frontend API

```text
HTML
  ↓
JavaScript
  ↓
XHR/fetch
  ↓
JSON
  ↓
application dates
```

Solution:

```text
discover the network request
validate that it is publicly accessible
extract structured JSON
```

## Case E: Access policy

```text
robots.txt
terms
authentication
explicit restriction
```

Solution:

```text
respect the restriction
```

Do not attempt to bypass it.

---

# 32. Browser-state lifecycle

Implement a safe lifecycle:

```text
First run
    |
    v
Start Chromium
    |
    v
University website
    |
    v
Challenge?
   / \
 yes  no
  |    |
human   |
interaction
  |    |
  +----+
    |
    v
Successful page
    |
    v
Save legitimate browser state
    |
    v
Future run
    |
    v
Restore state
    |
    v
Website
    |
    +---- expired ----> manual interaction again
    |
    v
Extract dates
```

Do not assume stored browser state remains valid indefinitely.

---

# 33. Performance strategy

The crawler should minimize browser usage.

Preferred sequence:

```text
HTTP request
    |
    +-- successful useful HTML --> parse
    |
    +-- structured public data --> parse
    |
    +-- JS/challenge/incomplete --> Playwright
```

Do not launch Chromium for every URL if a normal HTTP request is sufficient.

Use browser contexts efficiently.

Avoid opening unnecessary tabs/pages.

Use reasonable timeouts.

---

# 34. Security boundaries

The implementation must explicitly reject these approaches:

```text
CAPTCHA solving
Turnstile token forging
Cloudflare bypass
challenge token extraction
fingerprint spoofing
TLS fingerprint spoofing
proxy rotation for evasion
stolen cookies
cookie replay from another user
authentication bypass
private API access
security-control disabling
challenge JavaScript modification
```

If access remains unavailable after legitimate browser interaction:

```text
MANUAL_INTERVENTION_REQUIRED
```

or:

```text
ACCESS_RESTRICTED
```

should be returned.

Do not fabricate application dates.

---

# 35. Exact implementation workflow

Follow this order.

### Step 1

Inspect the complete existing repository.

### Step 2

Read `STATUS.md`.

### Step 3

Identify the exact current failure for each affected university.

### Step 4

Determine whether each failure is:

```text
JavaScript rendering
browser challenge
rate limiting
HTTP blocking
API discovery issue
HTML parsing issue
date parsing issue
```

### Step 5

Research the relevant official documentation.

### Step 6

Add or improve the HTTP fallback.

### Step 7

Add Playwright Chromium fallback.

### Step 8

Add challenge detection.

### Step 9

Add visible/manual challenge handling.

### Step 10

Add secure browser-state persistence.

### Step 11

Add network request/response inspection.

### Step 12

Identify public structured APIs where available.

### Step 13

Add JSON extraction.

### Step 14

Improve HTML extraction.

### Step 15

Add date normalization and validation.

### Step 16

Add explicit scraper/application statuses.

### Step 17

Add rate limiting and exponential backoff.

### Step 18

Add per-domain throttling.

### Step 19

Add evidence capture.

### Step 20

Add change detection.

### Step 21

Add tests.

### Step 22

Run the scraper against representative universities.

### Step 23

Compare the results with the official pages manually.

### Step 24

Document any remaining university-specific limitations.

---

# 36. Acceptance criteria

The implementation is complete when all of the following work:

* A normal university page can be fetched without Chromium when possible.
* JavaScript-only pages work through Playwright.
* Browser challenges are detected.
* Browser challenges are not incorrectly interpreted as "no application dates".
* A visible browser can be used for legitimate manual challenge completion.
* Successful browser state can be persisted securely.
* Expired browser state can trigger manual interaction again.
* Page network requests can be inspected.
* Public structured JSON data can be identified and extracted where appropriate.
* Application opening dates can be extracted.
* Application closing dates can be extracted.
* Semester/intake information can be extracted where available.
* Program-specific deadlines can be distinguished from unrelated dates.
* Dates are normalized.
* Ambiguous dates are not silently guessed.
* Rolling admissions are represented correctly.
* Previous and current dates can be compared.
* Actual date changes generate change events.
* 403/429/503/challenge states are not incorrectly classified as "application closed" or "not open".
* Rate limiting is handled with backoff.
* Domains are throttled.
* Evidence is retained for extracted dates.
* Browser state is protected from Git.
* Tests cover major success and failure paths.
* Logging provides enough information to diagnose failures.
* No security-control bypass is implemented.

---

# 37. Required final response after implementation

After implementing the changes, provide a technical report containing:

## Existing implementation

Explain:

* current architecture;
* existing packages;
* existing scraper flow;
* existing university adapters;
* existing date extraction;
* existing storage.

## Problems found

For every affected university explain:

```text
University
URL
Current behavior
HTTP status
Browser behavior
Challenge type, if identified
Actual cause
```

Do not claim that a site uses Cloudflare or another provider unless it was actually verified.

## Changes made

List:

* files changed;
* files added;
* packages added;
* functions added;
* classes added;
* configuration added;
* database changes;
* browser-state handling;
* challenge detection;
* network discovery;
* date extraction;
* retry/backoff;
* throttling;
* tests.

## Technical flow

Show:

```text
HTTP
 ↓
classification
 ↓
Playwright fallback
 ↓
challenge detection
 ↓
manual interaction if required
 ↓
network/API discovery
 ↓
HTML/JSON extraction
 ↓
date normalization
 ↓
validation
 ↓
storage
 ↓
change detection
```

## Verification

For every tested university provide:

```text
University
HTTP mode or browser mode
Challenge encountered?
Manual intervention required?
Extraction method
Opening date
Closing date
Semester/intake
Final scraper status
Evidence source
```

Do not invent results.

---

# 38. Final principle

The project should be a reliable **official-university application-date monitoring system**, not a bot-defense bypass system.

The preferred strategy is:

```text
Official public university page
        ↓
Normal HTTP request
        ↓
If insufficient
        ↓
Real Chromium browser
        ↓
Normal JavaScript/browser execution
        ↓
If challenge appears
        ↓
Human completes challenge normally
        ↓
Continue legitimate session
        ↓
Inspect page/network
        ↓
Use public HTML/JSON data
        ↓
Extract application dates
        ↓
Validate dates
        ↓
Store evidence
        ↓
Compare with previous crawl
        ↓
Notify on actual changes
```

Preserve all existing working functionality and make the smallest necessary architectural changes.

The implementation must prioritize correctness, traceability, low request volume, reliable failure classification, and accurate application-date extraction.
