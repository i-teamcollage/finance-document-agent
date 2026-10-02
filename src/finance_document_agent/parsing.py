"""Dates, amounts and payment terms in English, French and German, tolerant of scan errors."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

# Characters a scanner puts where a digit should be. Only ever translated inside number-shaped text.
_D = "[0-9OoIlSBZ|]"
_TO_DIGITS = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8", "Z": "2"})

MONTHS = {
    # English
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # French
    "janvier": 1, "janv": 1, "février": 2, "fevrier": 2, "févr": 2, "mars": 3, "avril": 4, "avr": 4,
    "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12, "decembre": 12, "déc": 12,
    # German
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "mär": 3, "juni": 6, "juli": 7, "oktober": 10,
    "okt": 10, "dezember": 12, "dez": 12,
}
_MONTH = "|".join(sorted((re.escape(name) for name in MONTHS), key=len, reverse=True))

_DATE_PATTERNS = [
    ("ymd", re.compile(rf"(?<![0-9])({_D}{{4}})-({_D}{{2}})-({_D}{{2}})(?![0-9])")),
    ("dmy", re.compile(rf"(?<![0-9A-Za-z])({_D}{{1,2}})[./]({_D}{{1,2}})[./]({_D}{{4}})(?![0-9])")),
    ("d_month_y", re.compile(rf"(?<![0-9A-Za-z])({_D}{{1,2}})(?:st|nd|rd|th|er|\.)?\s+({_MONTH})\.?\s+({_D}{{4}})(?![0-9])", re.I)),
    ("month_d_y", re.compile(rf"\b({_MONTH})\.?\s+({_D}{{1,2}})(?:st|nd|rd|th)?,?\s+({_D}{{4}})(?![0-9])", re.I)),
]


def fix_digits(text: str) -> str:
    return text.translate(_TO_DIGITS)


def _to_date(kind: str, groups: tuple[str, ...]) -> date | None:
    try:
        if kind == "ymd":
            year, month, day = (int(fix_digits(g)) for g in groups)
        elif kind == "dmy":
            day, month, year = (int(fix_digits(g)) for g in groups)
        elif kind == "d_month_y":
            day, month, year = int(fix_digits(groups[0])), MONTHS[groups[1].lower()], int(fix_digits(groups[2]))
        else:
            month, day, year = MONTHS[groups[0].lower()], int(fix_digits(groups[1])), int(fix_digits(groups[2]))
        return date(year, month, day)
    except (ValueError, KeyError):
        return None


def parse_date(text: str) -> date | None:
    text = text.strip()
    for kind, pattern in _DATE_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return _to_date(kind, match.groups())
    return None


def find_dates(text: str) -> list[tuple[str, date]]:
    """Every date in the text, as (exact quote, date), in reading order."""
    spans = []
    for kind, pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            value = _to_date(kind, match.groups())
            if value is not None:
                spans.append((match.start(), match.end(), match.group(0), value))
    spans.sort(key=lambda span: (span[0], -span[1]))
    found, last_end = [], -1
    for start, end, quote, value in spans:
        if start >= last_end:
            found.append((quote, value))
            last_end = end
    return found


_NUMBER = rf"(?:{_D}{{1,3}}(?:[.,   ']{_D}{{3}})+|{_D}+)(?:[.,]{_D}{{2}})?"
_CURRENCY = r"€|EUR|£|GBP"
_AMOUNT = re.compile(
    rf"(?P<c1>{_CURRENCY})\s?(?P<n1>{_NUMBER})|(?P<n2>{_NUMBER})\s?(?P<c2>{_CURRENCY})"
)
_CURRENCIES = {"€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}


def _to_decimal(number: str) -> Decimal:
    digits = fix_digits(number)
    decimal_part = re.search(r"[.,](\d{2})$", digits)
    if decimal_part:
        whole = re.sub(r"[^0-9]", "", digits[: decimal_part.start()])
        return Decimal(f"{whole}.{decimal_part.group(1)}")
    return Decimal(re.sub(r"[^0-9]", "", digits)).quantize(Decimal("0.01"))


def _from_match(match: re.Match) -> tuple[Decimal, str]:
    number = match.group("n1") or match.group("n2")
    currency = match.group("c1") or match.group("c2")
    return _to_decimal(number), _CURRENCIES[currency]


def parse_amount(text: str) -> tuple[Decimal, str] | None:
    match = _AMOUNT.fullmatch(text.strip())
    return _from_match(match) if match else None


def find_amounts(text: str) -> list[tuple[str, Decimal, str]]:
    """Every amount with a currency, as (exact quote, value, ISO currency), in reading order."""
    return [(match.group(0), *_from_match(match)) for match in _AMOUNT.finditer(text)]


_N = rf"({_D}{{1,3}})"
_TERMS = [
    re.compile(rf"(?<![A-Za-z]){_N}\s+days?\s+net", re.I),
    re.compile(rf"\bnet\s+{_N}(?![A-Za-z0-9])", re.I),
    re.compile(rf"within\s+{_N}\s+days", re.I),
    re.compile(rf"innerhalb\s+(?:von\s+)?{_N}\s+Tag", re.I),
    re.compile(rf"(?<![A-Za-z]){_N}\s+Tage\s+netto", re.I),
    re.compile(rf"(?:à|sous)\s+{_N}\s+jours", re.I),
    re.compile(rf"(?<![A-Za-z]){_N}\s+jours\s+net", re.I),
]


def days_from_terms(text: str) -> int | None:
    """Payment terms such as "30 days net" or "Zahlbar innerhalb von 14 Tagen" as a number of days."""
    for pattern in _TERMS:
        match = pattern.search(text)
        if match:
            digits = fix_digits(match.group(1))
            if digits.isdigit():
                return int(digits)
    return None
