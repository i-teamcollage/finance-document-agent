"""The vendor master: who we already pay, and to which bank account."""

from __future__ import annotations

import csv
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

LEGAL_FORMS = frozenset(
    "ltd limited plc llp llc inc sas sasu sarl eurl sa sca snc gmbh ag kg co ohg ug bv nv vof srl spa bvba sprl".split()
)
MATCH_THRESHOLD = 0.9


def normalize_name(name: str) -> str:
    """Company name without case, accents, punctuation or trailing legal form."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace(".", "")
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    while tokens and tokens[-1] in LEGAL_FORMS:
        tokens.pop()
    return " ".join(tokens)


class VendorMaster:
    def __init__(self, rows: list[dict[str, str]]):
        self.vendors = [dict(row, normalized=normalize_name(row["name"])) for row in rows]

    @classmethod
    def from_csv(cls, path: str | Path) -> VendorMaster:
        with open(path, newline="", encoding="utf-8") as handle:
            return cls(list(csv.DictReader(handle)))

    def match(self, name: str) -> dict[str, str] | None:
        """The vendor this name refers to, tolerating a scan error or two; None for a new counterparty."""
        wanted = normalize_name(name)
        if not wanted:
            return None
        best, best_score = None, 0.0
        for vendor in self.vendors:
            score = SequenceMatcher(None, wanted, vendor["normalized"]).ratio()
            if score > best_score:
                best, best_score = vendor, score
        return best if best_score >= MATCH_THRESHOLD else None
