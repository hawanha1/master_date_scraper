Master Prompt: Robust Web Scraper for University Admission Dates

Copy and paste the prompt below into an LLM/AI coding assistant (like ChatGPT, Claude, or GitHub Copilot) to generate a tailored, anti-bot resilient web scraping script for extracting university application dates.

Act as a Senior Python Developer specializing in web scraping, data extraction, and bypassing anti-bot systems (like Cloudflare, Akamai, and Imperva). 

### Objective
I need a Python script to extract application opening and closing dates for university admissions from specific web pages. Standard `requests` or `selenium` setups are currently getting blocked by anti-bot checks (HTTP 403, 429, CAPTCHAs, or JS challenges).

### Constraints & Technical Requirements
1. **Anti-Bot Mitigation:**
   - Use `curl_cffi` (for impersonating Chrome TLS/JA3 fingerprints) if the target page is largely static/HTML-rendered.
   - Use `nodriver` or `SeleniumBase` (in UC / Undetected Mode) if the page relies heavily on dynamic JavaScript rendering or Cloudflare Turnstile.
   - Do NOT use standard `requests` or default `selenium.webdriver`, as they are easily flagged.

2. **Stealth & Reliability Headers:**
   - Implement realistic browser headers (`User-Agent`, `Accept-Language`, `Sec-Ch-Ua`).
   - Include random delay intervals (human-like throttling) between actions using `time.sleep` or `asyncio.sleep`.

3. **Data Parsing:**
   - Use `BeautifulSoup4` or `selectolax` to parse the fetched HTML.
   - Extract text content specifically related to:
     - Application Start / Opening Date
     - Application Deadline / Closing Date
     - Admission Status (Open / Closed / Coming Soon)

4. **Code Structure:**
   - Write clean, production-ready Python code with clear error handling (handling time-outs, non-200 HTTP statuses, and missing HTML tags gracefully).
   - Structured output format: Clean dictionary or JSON output containing `{ "university": "...", "status": "...", "opening_date": "...", "closing_date": "..." }`.

### Target Details
- Target URL: [INSERT UNIVERSITY URL HERE]
- Target HTML Element/Text hints (optional): [INSERT CSS SELECTOR OR KEYWORDS HERE, e.g., "Deadlines section"]

Please provide:
1. The full Python script using the most optimal approach (`curl_cffi` or `nodriver`).
2. Instructions on installing all required packages via `pip`.
3. Guidance on how to execute and adapt the script for multiple university URLs.
