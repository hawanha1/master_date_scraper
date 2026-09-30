"""
Find admission / application windows (opening date -> closing date) in page text.
Works natively in Italian, German and English, so no translation step is needed.

Recognised forms, for example:
    Immatricolazioni dal 15 luglio al 30 settembre 2026
    Bewerbungszeitraum: 01.06.2026 – 15.07.2026
    Bewerbungsfrist Wintersemester 2026/27: 15. Juli      (year from "2026/27")
    Applications open 1 February 2026, deadline 31 May 2026
    Scadenza domande: 12/09/2026
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    # english
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # italian
    "gennaio": 1, "genn": 1, "febbraio": 2, "febbr": 2, "marzo": 3, "aprile": 4, "maggio": 5, "magg": 5,
    "giugno": 6, "giu": 6, "luglio": 7, "lug": 7, "agosto": 8, "ago": 8, "settembre": 9, "sett": 9,
    "ottobre": 10, "ott": 10, "novembre": 11, "dicembre": 12, "dic": 12,
    # german
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "okt": 10, "dezember": 12, "dez": 12,
}
MON = "(" + "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True)) + r")\.?(?![a-zäöü])"
DAY = r"(\d{1,2})(?:\.|º|°|st|nd|rd|th)?"
YEAR = r"(20\d{2})"

PATTERNS = [
    # 15 luglio 2026 / 15. Juli 2026 / 15 July, 2026
    ("dmy", re.compile(rf"\b{DAY}\s*(?:di\s+|de\s+)?{MON}\s*,?\s*{YEAR}\b", re.I)),
    # July 15, 2026
    ("mdy", re.compile(rf"\b{MON}\s+{DAY},?\s+{YEAR}\b", re.I)),
    # 2026-07-15
    ("iso", re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")),
    # 15.07.2026 / 15/07/2026 / 15-07-2026 / 15.07.26
    ("num", re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2}|\d{2})\b(?![./-]\d)")),
    # 15 luglio / 15. Juli  (year inferred)
    ("dm", re.compile(rf"\b{DAY}\s*(?:di\s+)?{MON}", re.I)),
    # 15.07. (German, year inferred)
    ("num_noyear", re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(?!\d)")),
]
RANGE_GAP = re.compile(
    r"^[\s,:]*(?:-|–|—|to|until|till|through|thru|and|al|all'|alle|fino al|fino alle|entro il|bis|bis zum|"
    r"bis einschließlich|bis spätestens|und)[\s,:]*$", re.I)
ACAD_YEAR = re.compile(r"(20\d{2})\s*[/–-]\s*(?:20)?(\d{2})(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

APPLY = re.compile(
    r"appl(?:y|ication|icants?)|admission|admitted|enrol+ment|registration|pre-?registration|call for"
    r"|candidatur\w*|immatricolazion\w*|iscrizion\w*|ammission\w*|preiscrizion\w*|domand[ae]|bando|bandi"
    r"|selezion\w*|test di ammissione|tolc|bewerb\w*|zulassung\w*|einschreib\w*|immatrikul\w*|anmeld\w*"
    r"|uni-assist|studienplatz\w*|hochschulstart", re.I)
DEADLINE = re.compile(
    r"deadline|closing|close[sd]?|until|no later than|last (?:day|date)|due"
    r"|scadenz\w*|entro|termine|chiusura|fino al|bewerbungsfrist|\bfrist\w*|bis zum|bis spätestens|spätestens"
    r"|ausschlussfrist|bewerbungsschluss|einsendeschluss", re.I)
OPEN = re.compile(
    r"\bopen(?:s|ing)?\b|\bfrom\b|\bstarts?\b|\bbegins?\b|apertur\w*|\bdal\b|a partire da\w*|\bdalle ore\b"
    r"|\bab\b|\bab dem\b|\bvom\b|beginn\w*|bewerbungszeitraum|bewerbungsphase|freigeschaltet", re.I)
EXCLUDE = re.compile(
    r"exam\w*|esam\w*|appell\w*|prüfung\w*|klausur\w*|lezion\w*|vorlesung\w*|lecture\w*|classes"
    r"|holiday\w*|ferien|vacanz\w*|festivit\w*|(?:sessione|seduta|esame|prova finale) di laurea|graduation|thesis|tesi\b|tasse|rata|fee[s]?\b"
    r"|gebühr\w*|beitrag|rückmeld\w*|stipend\w*|scholarship\w*|borse? di studio|housing|alloggi\w*"
    r"|wohnheim\w*|erasmus|exchange|mobilit\w*|incoming|outgoing|webinar|open day|evento|conference"
    r"|convegno|seminar\w*|workshop|dottorato|phd|doctoral|promotion|pubblicat\w*|published|updated"
    r"|aggiornat\w*|stand:|zuletzt|job|stellen|concorso|personale|staff|tirocini\w*|praktik\w*"
    r"|pagament\w*|payments?|winter school|summer school|spring school|award|premio|premi\b|eventi|thes[ei]s", re.I)


@dataclass
class Window:
    opens: date | None
    closes: date | None
    context: str
    url: str = ""

    def status(self, today: date, deadline_days: int, opened_days: int) -> str | None:
        """Why this window is relevant today, or None."""
        o, c = self.opens, self.closes
        if o and c:
            if o <= today <= c:
                return "OPEN NOW"
            if today < o <= today + timedelta(days=deadline_days):
                return "Opens soon"
            return None
        if c and today <= c <= today + timedelta(days=deadline_days):
            return "Deadline coming (opening date not stated)"
        if o and o <= today <= o + timedelta(days=opened_days):
            return "Opened recently (closing date not stated)"
        return None


def _mk(y, m, d) -> date | None:
    try:
        y = int(y)
        if y < 100:
            y += 2000
        return date(y, int(m), int(d))
    except (TypeError, ValueError):
        return None


def _infer_year(text: str, s: int, e: int, month: int) -> int | None:
    after = YEAR_RE.search(text[e:e + 50])
    if after:
        return int(after.group(1))
    near = text[max(0, s - 500):s]
    acad = [m for m in ACAD_YEAR.finditer(near) if int(m.group(2)) == (int(m.group(1)) + 1) % 100]
    if acad:
        y1 = int(acad[-1].group(1))
        return y1 if month >= 8 else y1 + 1
    before = list(YEAR_RE.finditer(text[max(0, s - 150):s]))
    return int(before[-1].group(1)) if before else None


def find_dates(text: str) -> list[tuple[int, int, date]]:
    taken: list[tuple[int, int]] = []
    out = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            s, e = m.span()
            if any(not (e <= a or s >= b) for a, b in taken):
                continue
            g = m.groups()
            d = None
            if name == "dmy":
                d = _mk(g[2], MONTHS[g[1].lower().rstrip(".")], g[0])
            elif name == "mdy":
                d = _mk(g[2], MONTHS[g[0].lower().rstrip(".")], g[1])
            elif name == "iso":
                d = _mk(g[0], g[1], g[2])
            elif name == "num":
                d = _mk(g[2], g[1], g[0])            # Italy & Germany write day first
            elif name == "dm":
                mo = MONTHS[g[1].lower().rstrip(".")]
                y = _infer_year(text, s, e, mo)
                d = _mk(y, mo, g[0]) if y else None
            elif name == "num_noyear":
                y = _infer_year(text, s, e, int(g[1]) if g[1].isdigit() else 0)
                d = _mk(y, g[1], g[0]) if y else None
            if d:
                taken.append((s, e))
                out.append((s, e, d))
    out.sort()
    return out


def _nearest(rx: re.Pattern, before: str, after: str) -> int | None:
    """Distance (chars) of the closest keyword; words after the date count double."""
    best = None
    for m in rx.finditer(before):
        dist = len(before) - m.end()
        best = dist if best is None else min(best, dist)
    for m in rx.finditer(after):
        dist = m.start() * 2 + 10
        best = dist if best is None else min(best, dist)
    return best


def find_windows(text: str, url: str = "", today: date | None = None) -> list[Window]:
    today = today or date.today()
    lo, hi = today - timedelta(days=400), today + timedelta(days=400)
    dates = [x for x in find_dates(text) if lo <= x[2] <= hi]
    windows: list[Window] = []
    singles: list[tuple[int, str, date]] = []
    i = 0
    while i < len(dates):
        s, e, d = dates[i]
        rng = None
        if i + 1 < len(dates):
            s2, e2, d2 = dates[i + 1]
            if RANGE_GAP.match(text[e:s2]) and d <= d2 <= d + timedelta(days=400):
                rng = (s2, e2, d2)
        end = rng[1] if rng else e
        before = text[max(0, s - 220):s]
        # "dal 1 luglio al 30 settembre": the 'dal' belongs to this range
        after = text[end:end + 80]
        ap = _nearest(APPLY, before, after)
        ex = _nearest(EXCLUDE, before[-90:], after[:40])
        if ap is None or (ex is not None and ex < ap):
            i += 2 if rng else 1
            continue
        ctx = (before[-160:] + "【" + text[s:end] + "】" + after[:60]).replace("\n", " ¶ ").strip()
        if rng:
            windows.append(Window(d, rng[2], ctx, url))
            i += 2
            continue
        dl, op = _nearest(DEADLINE, before[-120:], after[:40]), _nearest(OPEN, before[-60:], after[:20])
        if dl is not None and (op is None or dl <= op):
            singles.append((s, "close", d, ctx))
        elif op is not None:
            singles.append((s, "open", d, ctx))
        i += 1
    # pair "applications open 1 Feb ... deadline 31 May" when they are close together
    used = set()
    for a, (sa, ka, da, ca) in enumerate(singles):
        if ka != "open" or a in used:
            continue
        for b in range(a + 1, len(singles)):
            sb, kb, db, cb = singles[b]
            if sb - sa > 600:
                break
            if kb == "close" and b not in used and da < db <= da + timedelta(days=365):
                windows.append(Window(da, db, ca + " … " + cb, url))
                used.update({a, b})
                break
    for n, (_, kind, d, ctx) in enumerate(singles):
        if n not in used:
            windows.append(Window(d if kind == "open" else None, d if kind == "close" else None, ctx, url))
    return windows
