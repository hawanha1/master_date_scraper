"""
Reader for the country-tab university registry (Schengen_29_Public_Universities_complete.xlsx).

Layout: one tab per country (plus non-country tabs such as README / Sources). Each country tab
has a header row (`#`, `Public university / university-level institution`, `Type`,
`Public status`, `Country`) followed by one institution per row, sometimes with blank rows.

Institution names are written in several styles, so each one is parsed into a search name,
aliases and an acronym:
    University of Natural Resources and Life Sciences, Vienna (BOKU)   -> acronym BOKU
    Université des Antilles (University of the Antilles)               -> English alias
    Europa-Universität Viadrina Frankfurt (Oder)                       -> "(Oder)" is part of the name
    University of Osijek / Josip Juraj Strossmayer University of Osijek -> two aliases
    National University of Distance Education — UNED                   -> acronym UNED
    IUSS – Istituto Universitario di Studi Superiori di Pavia          -> acronym IUSS
    Medical University – Sofia                                          -> "Medical University Sofia"
    Academy of Music, Dance and Fine Arts “Prof. Asen Diamandiev”       -> curly quotes removed
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

DEFAULT_REGISTRY = Path(__file__).with_name("Schengen_29_Public_Universities_complete.xlsx")

_INSTITUTION_WORDS = re.compile(
    r"\b(universit\w*|college|school|academy|akademi\w*|institut\w*|hochschule|polytechnic|conservatoire)\b", re.I)
_KEY_STOPWORDS = {
    "university", "universite", "universitat", "universita", "universidad", "universiteit", "universitet",
    "of", "the", "and", "de", "di", "du", "des", "la", "le", "fur", "in", "from", "at", "a",
}


@dataclass
class UniEntry:
    country: str
    raw_name: str            # exactly as written in the sheet
    name: str                # cleaned name used for searching
    aliases: list[str] = field(default_factory=list)   # every usable form of the name, `name` first
    acronym: str = ""
    type: str = ""
    row: int = 0             # row number in the sheet (for traceability)
    duplicate_of: str = ""   # set when the same institution is listed twice in a tab


def fold(text: str) -> str:
    """Lower-case and strip accents: 'Tromsø Münster Łódź' -> 'tromso munster lodz'."""
    text = text.replace("ø", "o").replace("Ø", "O").replace("ł", "l").replace("Ł", "L").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _is_acronym(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 25 or len(s.split()) > 3:
        return False
    first = s.split()[0]
    uppers = sum(ch.isupper() for ch in first)
    return (uppers >= 2 and len(first) <= 12) or (first.islower() and first.isalpha() and len(first) <= 5)


def parse_name(raw: str) -> tuple[str, list[str], str]:
    """Return (search name, aliases, acronym) for a registry name."""
    s = raw.replace("“", "").replace("”", "").replace("„", "").replace('"', "")
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"\s+", " ", s).strip()
    acronym, extra = "", []

    # parentheses: acronym, translation, or part of the name ("Frankfurt (Oder)")
    def paren(m: re.Match) -> str:
        nonlocal acronym
        inner = m.group(1).strip()
        if _INSTITUTION_WORDS.search(inner) and len(inner.split()) >= 2:
            extra.append(inner)
            return ""
        if _is_acronym(inner):
            acronym = acronym or (inner if inner.isupper() else inner.split()[0])
            if len(inner.split()) > 1:
                extra.append(inner)          # "WU Vienna", "TU Darmstadt"
            return ""
        return " " + inner
    s = re.sub(r"\s*\(([^)]*)\)", paren, s).strip()

    # " / " alternative names (but not "Aarhus/Aalborg")
    parts = [p.strip() for p in re.split(r"\s+/\s+", s) if p.strip()]
    base = parts[0]
    extra += parts[1:]

    # dashes: "X — UNED" (acronym), "Medical University – Sofia" (city), "UiT – subtitle"
    dash = re.split(r"\s+[–—-]\s+", base)
    if len(dash) == 2:
        left, right = dash
        if _is_acronym(right) and len(right.split()) == 1:
            acronym, base = acronym or right, left
        elif _is_acronym(left) and len(left.split()) == 1:
            acronym, base = acronym or left, right
            extra.append(f"{left} {right}")
        elif _INSTITUTION_WORDS.search(left) and _INSTITUTION_WORDS.search(right) and len(left.split()) >= 3:
            base = left                      # "University of Tromsø – The Arctic University of Norway"
            extra.append(right)
        else:
            base = f"{left} {right}"         # "Medical University – Sofia"
    base = re.sub(r"\s+", " ", base).strip(" ,")
    aliases = [base] + [a for a in dict.fromkeys(e.strip(" ,") for e in extra) if a and a != base]
    return base, aliases, acronym


def _key(name: str) -> tuple[frozenset, str]:
    """(name tokens, city) — the trailing "in <City>" is kept apart."""
    n = fold(name)
    m = re.search(r"\s+in\s+(\w+)$", n)
    city = m.group(1) if m else ""
    n = n[:m.start()] if m else n
    return frozenset(t for t in re.findall(r"[a-z0-9]+", n) if t not in _KEY_STOPWORDS), city


def _same_institution(a: UniEntry, b: UniEntry) -> bool:
    for (x, cx) in map(_key, a.aliases):
        for (y, cy) in map(_key, b.aliases):
            if cx and cy and cx != cy:
                continue                     # "Academy ... in Poznan" vs "Academy ... in Krakow"
            if x == y:
                return True
            small, big = sorted((x, y), key=len)
            # "Paris-Panthéon-Assas" vs "Paris 2 Panthéon-Assas": differ only by a number
            if len(small) >= 3 and small < big and all(t.isdigit() for t in big - small):
                return True
    return False


def _find_header(rows: list[tuple]) -> tuple[int, dict] | None:
    for i, r in enumerate(rows[:15]):
        cells = [str(v).strip() if v is not None else "" for v in r]
        if sum(1 for c in cells if c) < 3:
            continue
        cols = {}
        for j, c in enumerate(cells):
            lc = c.lower()
            if "name" not in cols and re.search(r"universit|institution", lc):
                cols["name"] = j
            elif lc == "type" or lc.startswith("type"):
                cols["type"] = j
            elif lc == "country":
                cols["country"] = j
        if "name" in cols:
            return i, cols
    return None


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> dict[str, list[UniEntry]]:
    """{country: [UniEntry, ...]} in sheet order; duplicates are kept but flagged."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    registry: dict[str, list[UniEntry]] = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        found = _find_header(rows)
        if not found:
            continue                     # README, Sources, ...
        hdr, cols = found
        entries: list[UniEntry] = []
        for offset, r in enumerate(rows[hdr + 1:], start=hdr + 2):
            raw = r[cols["name"]] if cols["name"] < len(r) else None
            if not isinstance(raw, str) or not raw.strip():
                continue
            country = ws.title.strip()
            if "country" in cols and cols["country"] < len(r) and isinstance(r[cols["country"]], str):
                country = r[cols["country"]].strip() or country
            name, aliases, acronym = parse_name(raw)
            typ = r[cols["type"]] if "type" in cols and cols["type"] < len(r) else ""
            e = UniEntry(country, raw.strip(), name, aliases, acronym, str(typ or "").strip(), offset)
            dup = next((x for x in entries if not x.duplicate_of and _same_institution(x, e)), None)
            if dup:
                e.duplicate_of = dup.raw_name
            entries.append(e)
        if entries:
            registry[ws.title.strip()] = entries
    wb.close()
    return registry


def parse_selection(text: str, n: int) -> list[int]:
    """'' / 'all' -> everything; '1-5,8,12' -> those (1-based) positions."""
    text = text.strip().lower()
    if text in ("", "all", "a", "*"):
        return list(range(n))
    picked: list[int] = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            picked += range(int(a) - 1, min(int(b), n))
        else:
            picked.append(int(part) - 1)
    return [i for i in dict.fromkeys(picked) if 0 <= i < n]


def match_country(answer: str, countries: list[str]) -> str | None:
    answer = answer.strip()
    if answer.isdigit() and 1 <= int(answer) <= len(countries):
        return countries[int(answer) - 1]
    exact = [c for c in countries if fold(c) == fold(answer)]
    if exact:
        return exact[0]
    starts = [c for c in countries if fold(c).startswith(fold(answer))] if answer else []
    return starts[0] if len(starts) == 1 else None
