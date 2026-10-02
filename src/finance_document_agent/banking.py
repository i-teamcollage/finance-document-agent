"""Bank details that can be proven: IBAN check digits, country formats, and a bank directory."""

from __future__ import annotations

import csv
import re
from pathlib import Path

# Length and BBAN format per country (ISO 13616 registry, the countries this sample uses and neighbours).
IBAN_FORMATS = {
    "AT": (20, r"\d{16}"),
    "BE": (16, r"\d{12}"),
    "DE": (22, r"\d{18}"),
    "ES": (24, r"\d{20}"),
    "FR": (27, r"\d{10}[A-Z0-9]{11}\d{2}"),
    "GB": (22, r"[A-Z]{4}\d{14}"),
    "IE": (22, r"[A-Z]{4}\d{14}"),
    "IT": (27, r"[A-Z]\d{10}[A-Z0-9]{12}"),
    "LU": (20, r"\d{3}[A-Z0-9]{13}"),
    "NL": (18, r"[A-Z]{4}\d{10}"),
    "NO": (15, r"\d{11}"),
    "PT": (25, r"\d{21}"),
}

# Where the bank code sits inside the IBAN, per country.
BANK_CODE_SLICES = {
    "AT": slice(4, 9),
    "BE": slice(4, 7),
    "DE": slice(4, 12),
    "ES": slice(4, 8),
    "FR": slice(4, 9),
    "GB": slice(4, 8),
    "IE": slice(4, 8),
    "IT": slice(5, 10),
    "LU": slice(4, 7),
    "NL": slice(4, 8),
}

# What a scanner typically reads instead of the real character, reversed: noisy -> possible originals.
OCR_ORIGINALS = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "B": "8",
    "0": "OD", "1": "IL", "2": "Z", "5": "S", "6": "G", "8": "B",
}

_BIC = re.compile(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?")


def normalize_iban(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97


def iban_is_valid(text: str) -> bool:
    iban = normalize_iban(text)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban):
        return False
    country_format = IBAN_FORMATS.get(iban[:2])
    if country_format is None:
        return False
    length, bban_pattern = country_format
    if len(iban) != length or not re.fullmatch(bban_pattern, iban[4:]):
        return False
    if iban[2:4] in ("00", "01", "99"):
        return False
    return _mod97(iban) == 1


def make_iban(country: str, bban: str) -> str:
    check = 98 - _mod97(f"{country}00{bban}")
    return f"{country}{check:02d}{bban}"


def bank_code(text: str) -> str | None:
    iban = normalize_iban(text)
    position = BANK_CODE_SLICES.get(iban[:2])
    return iban[position] if position else None


def bic_format_ok(text: str) -> bool:
    return bool(_BIC.fullmatch(re.sub(r"\s+", "", text).upper()))


def bic11(text: str) -> str:
    bic = re.sub(r"\s+", "", text).upper()
    return bic + "XXX" if len(bic) == 8 else bic


class BankDirectory:
    """Which BIC belongs to which bank code. A client build loads the official SEPA/SWIFT files."""

    def __init__(self, rows: list[dict[str, str]]):
        self._bics = {(row["country"], row["bank_code"]): bic11(row["bic"]) for row in rows}
        self.names = {(row["country"], row["bank_code"]): row["name"] for row in rows}

    @classmethod
    def from_csv(cls, path: str | Path) -> BankDirectory:
        with open(path, newline="", encoding="utf-8") as handle:
            return cls(list(csv.DictReader(handle)))

    def bic_for(self, iban: str) -> str | None:
        normalized = normalize_iban(iban)
        return self._bics.get((normalized[:2], bank_code(normalized) or ""))

    def bic_matches(self, iban: str, bic: str) -> bool:
        expected = self.bic_for(iban)
        return expected is not None and expected == bic11(bic)


def repair_iban(text: str, directory: BankDirectory) -> list[str]:
    """Single-character scan repairs that make the check digits and the directory agree.

    The result is a suggestion for a reviewer, never an automatic acceptance.
    """
    iban = normalize_iban(text)
    if iban_is_valid(iban):
        return []
    candidates = set()
    for position, character in enumerate(iban):
        for original in OCR_ORIGINALS.get(character, ""):
            candidate = iban[:position] + original + iban[position + 1 :]
            if iban_is_valid(candidate) and directory.bic_for(candidate) is not None:
                candidates.add(candidate)
    return sorted(candidates)
