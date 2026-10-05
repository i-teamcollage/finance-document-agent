"""Plain rules that find format-bound values. Their findings are hints for the model and
a second opinion for the checks; they never accept anything on their own."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .banking import IBAN_FORMATS, bic11, normalize_iban
from .parsing import find_amounts, find_dates

_IBAN = re.compile(r"\b[A-Z]{2}[0-9OoIlSBZ]{2}(?: ?[A-Za-z0-9]{4}){2,7}(?: ?[A-Za-z0-9]{1,4})?\b")
_BIC = re.compile(
    r"(?:B[I1l]C|SW[I1l]FT)(?:\s*/\s*(?:B[I1l]C|SW[I1l]FT))?(?:-Code)?\s*:?\s*([A-Z0-9]{8}(?:[A-Z0-9]{3})?)\b"
)
_DOC_NUMBER = re.compile(
    r"(?:Invoice No|Invoice number|Agreement No\.?|Our reference|Facture n°|FACTURE N°|Contrat n°|notre réf\.?"
    r"|Rechnungsnummer|Rechnung Nr\.|Vertrag Nr\.|unser Zeichen)\s*:?\s*([A-Z0-9][A-Za-z0-9/\-.]{2,30})",
    re.IGNORECASE,
)
_VAT_LABEL = re.compile(r"\b(?:VAT|TVA|USt|MwSt)\b")
_TOTAL_LABEL = re.compile(
    r"Total due|Amount payable|Total TTC|Net à payer|Montant TTC|Rechnungsbetrag|Gesamtbetrag", re.IGNORECASE
)


@dataclass
class Candidates:
    ibans: list[str] = field(default_factory=list)
    bics: list[str] = field(default_factory=list)
    dates: list[tuple[str, date]] = field(default_factory=list)
    amounts: list[tuple[str, Decimal, str]] = field(default_factory=list)
    document_numbers: list[str] = field(default_factory=list)
    has_vat_breakdown: bool = False
    labelled_totals: list[tuple[Decimal, str]] = field(default_factory=list)


def find_candidates(text: str) -> Candidates:
    ibans = []
    for match in _IBAN.finditer(text):
        candidate = normalize_iban(match.group(0))
        expected = IBAN_FORMATS.get(candidate[:2])
        if expected and len(candidate) == expected[0] and candidate not in ibans:
            ibans.append(candidate)
    bics = list(dict.fromkeys(bic11(match.group(1)) for match in _BIC.finditer(text)))
    numbers = list(dict.fromkeys(match.group(1).rstrip(".,") for match in _DOC_NUMBER.finditer(text)))
    totals = []
    for line in text.splitlines():
        if _TOTAL_LABEL.search(line):
            totals += [(value, currency) for _, value, currency in find_amounts(line)]
    return Candidates(
        ibans=ibans,
        bics=bics,
        dates=find_dates(text),
        amounts=find_amounts(text),
        document_numbers=numbers,
        has_vat_breakdown=bool(_VAT_LABEL.search(text)),
        labelled_totals=totals,
    )


def describe(candidates: Candidates) -> str:
    """The rules' findings, as plain text for the prompt."""

    def listing(items: list[str]) -> str:
        return ", ".join(items) if items else "none found"

    return "\n".join(
        [
            f"IBAN-like strings: {listing(candidates.ibans)}",
            f"BIC next to a BIC/SWIFT label: {listing(candidates.bics)}",
            f"Dates: {listing([f'{quote} = {value.isoformat()}' for quote, value in candidates.dates])}",
            f"Amounts: {listing([f'{quote} = {value} {currency}' for quote, value, currency in candidates.amounts])}",
            f"Numbers next to a document-number label: {listing(candidates.document_numbers)}",
        ]
    )
