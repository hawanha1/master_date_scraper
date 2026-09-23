"""
Native-language date and keyword support, so extraction works even when translation is
unavailable (the free Google endpoint rate-limits at ~5 requests/second).

- month names for every registry language come from dateparser's locale data (with
  declensions: Polish "października", Czech "října", Finnish "lokakuuta", ...)
- admission keywords (course start / application deadline / applications open / noise)
  are hand-written for the main languages of the 29 Schengen countries
"""
from __future__ import annotations

import re
from functools import lru_cache

from dateparser.languages import default_loader

LANGS = ["it", "de", "fr", "es", "pt", "nl", "pl", "cs", "sk", "sl", "hr", "hu", "ro", "sv", "da",
         "nb", "fi", "et", "lv", "lt", "el", "bg", "is"]
_MONTH_KEYS = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]
_EN_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


@lru_cache(maxsize=None)
def month_map(croatian: bool = False) -> dict[str, int]:
    """name -> month number for English + all registry languages.

    Native names shorter than 4 letters are left out (Italian "set", Portuguese "out" collide
    with ordinary words). "listopad" is November in Czech/Polish but October in Croatian.
    """
    names: dict[str, int] = {}
    for lang in LANGS:
        try:
            info = default_loader.get_locale(lang).info
        except Exception:  # noqa: BLE001
            continue
        for num, key in enumerate(_MONTH_KEYS, 1):
            for n in info.get(key, []):
                n = n.lower().rstrip(".")
                if len(n) >= 4 and n.isalpha() and n not in names:
                    names[n] = num
    for n in list(names):
        if n.startswith("listopad"):
            names[n] = 10 if croatian else 11
    names.update({"mai": 5, "maj": 5, "mei": 5})   # full 3-letter May names (fr/de/ro, sv/pl/da, nl)
    names.update(_EN_MONTHS)
    return names


@lru_cache(maxsize=None)
def month_regex() -> str:
    """Alternation of every month name (longest first), ending on a non-letter."""
    alts = sorted(month_map(), key=len, reverse=True)
    return "(" + "|".join(re.escape(a) for a in alts) + r")\.?(?![^\W\d_])"


# Admission vocabulary per language (lower-case regex fragments).
NATIVE = {
    "start": [
        # it
        r"inizio (?:delle |dei |del )?(?:lezioni|corsi|attività didattiche|semestre|anno accademico)",
        r"avvio (?:delle )?lezioni", r"periodo (?:delle |di )?lezioni", r"primo semestre", r"inizio attività",
        # de
        r"vorlesungsbeginn", r"vorlesungszeit", r"semesterbeginn", r"studienbeginn", r"lehrbeginn",
        r"beginn der (?:vorlesungen|lehrveranstaltungen|vorlesungszeit)", r"lehrveranstaltungsbeginn",
        # fr
        r"rentrée(?: universitaire| académique)?", r"début des (?:cours|enseignements)", r"début du semestre",
        # es / pt
        r"inicio (?:de (?:las )?clases|del curso|del semestre|del cuatrimestre|das aulas|do semestre|do ano letivo)",
        r"comienzo de (?:las )?clases", r"início das aulas", r"início do (?:semestre|ano letivo)",
        # nl
        r"start (?:van )?(?:het )?(?:collegejaar|academiejaar|semester)", r"begin (?:van )?de colleges",
        r"aanvang (?:van )?(?:het )?(?:academiejaar|collegejaar)",
        # pl / cs / sk / sl / hr
        r"rozpoczęcie (?:roku akademickiego|zajęć|semestru)", r"początek (?:zajęć|semestru)", r"inauguracja",
        r"zahájení (?:výuky|semestru|akademického roku)", r"začátek (?:výuky|semestru)",
        r"začiatok (?:výučby|semestra)", r"začetek (?:predavanj|študijskega leta)", r"početak (?:nastave|semestra)",
        # hu / ro
        r"szorgalmi időszak", r"első tanítási nap", r"félév kezdete", r"tanév kezdete",
        r"începerea cursurilor", r"începutul (?:anului universitar|cursurilor|semestrului)", r"deschiderea anului",
        # sv / da / nb / fi / et / lv / lt / is
        r"terminsstart", r"kursstart", r"terminen (?:börjar|startar)", r"studiestart", r"semesterstart",
        r"undervisningen starter", r"lukukausi alkaa", r"opetus alkaa", r"lukuvuosi alkaa",
        r"õppetöö algus", r"semestri algus", r"studiju sākums", r"mokslo metų pradžia", r"kennsla hefst",
    ],
    "deadline": [
        r"scadenza", r"entro il", r"termine (?:ultimo )?(?:per|di presentazione)", r"chiusura (?:delle )?(?:iscrizioni|domande|candidature|immatricolazioni)",
        r"bewerbungsfrist", r"bewerbungsschluss", r"einsendeschluss", r"ausschlussfrist", r"spätestens",
        r"date limite", r"clôture (?:des )?(?:candidatures|inscriptions)", r"au plus tard",
        r"plazo(?: de (?:solicitud|inscripción|preinscripción|matrícula))?", r"fecha límite", r"cierre de (?:la )?(?:inscripción|preinscripción)",
        r"prazo(?: de candidatura)?", r"data limite",
        r"aanmelddeadline", r"uiterlijk", r"sluitingsdatum",
        r"termin (?:składania|rejestracji|zgłoszeń)", r"rejestracja (?:trwa )?do",
        r"termín (?:podání|podávání) přihlášek", r"uzávěrka přihlášek", r"termín podania prihlášok",
        r"rok za prijavo", r"rok za prijave", r"jelentkezési határidő", r"beadási határidő",
        r"termen(?:ul)? (?:limită|de înscriere)", r"data limită",
        r"sista (?:anmälnings|ansöknings)dag", r"ansøgningsfrist", r"søknadsfrist", r"hakuaika päättyy",
        r"haku päättyy", r"hakuaika (?:on )?\d", r"sisseastumise tähtaeg", r"pieteikšanās termiņš", r"umsóknarfrestur",
    ],
    "open": [
        r"apertura (?:delle )?(?:iscrizioni|candidature|immatricolazioni|domande)", r"a partire dal",
        r"bewerbungszeitraum", r"bewerbungsbeginn", r"bewerbungsphase",
        r"ouverture (?:des )?(?:candidatures|inscriptions)", r"apertura de (?:la )?(?:inscripción|preinscripción)",
        r"abertura (?:das )?candidaturas", r"aanmelden (?:kan )?vanaf", r"rejestracja (?:rozpoczyna się|od)",
        r"anmälan öppnar", r"hakuaika alkaa", r"haku alkaa",
    ],
    "excl": [
        r"esami", r"appello", r"sessione (?:di )?laurea", r"lauree", r"vacanze", r"festività", r"sospensione",
        r"tasse", r"pagamento", r"rata", r"fine (?:delle )?lezioni", r"termine delle lezioni",
        r"prüfung\w*", r"klausur\w*", r"ferien", r"rückmeldung", r"gebühr\w*", r"vorlesungsfrei\w*",
        r"ende der vorlesungszeit", r"examens?", r"vacances", r"fin des cours", r"exámenes", r"vacaciones",
        r"fin de (?:las )?clases", r"exames", r"férias", r"tentamens?", r"egzamin\w*", r"sesja", r"zkouš\w*",
        r"vizsg\w*", r"examen\w*", r"sesiune", r"tentamen\w*", r"eksamen\w*", r"tentti\w*", r"eksam\w*",
    ],
    "intake": [
        r"immatricolazion\w*", r"ammission\w*", r"iscrizion\w*", r"preiscrizion\w*", r"bando",
        r"zulassung\w*", r"bewerbung\w*", r"einschreibung\w*", r"inscription\w*", r"candidature\w*",
        r"admisi[óo]n\w*", r"matr[íi]cula\w*", r"preinscripci[óo]n\w*", r"candidatura\w*", r"inschrijving\w*",
        r"aanmelding\w*", r"rekrutacj\w*", r"přijímací\w*", r"prijímacie\w*", r"felvételi\w*", r"admitere",
        r"antagning\w*", r"optagelse\w*", r"opptak\w*", r"sisäänotto\w*", r"vastuuvõtt\w*", r"uzņemšan\w*", r"priėmim\w*",
    ],
}


def native_alternation(kind: str) -> str:
    return "|".join(NATIVE[kind])
