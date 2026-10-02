"""The one model call per document: read the fields and quote where each one came from."""

from __future__ import annotations

from typing import Any

from .llm import LLM, Reply
from .rules import Candidates, describe
from .schema import validate

_QUOTED = {
    "type": "object",
    "properties": {"value": {"type": ["string", "null"]}, "quote": {"type": ["string", "null"]}},
    "required": ["value", "quote"],
    "additionalProperties": False,
}
_AMOUNT = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"], "enum": ["EUR", "GBP", None]},
        "quote": {"type": ["string", "null"]},
    },
    "required": ["value", "currency", "quote"],
    "additionalProperties": False,
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "counterparty": _QUOTED,
        "document_number": _QUOTED,
        "document_date": _QUOTED,
        "due_date": _QUOTED,
        "amount": _AMOUNT,
        "iban": _QUOTED,
        "bic": _QUOTED,
    },
    "required": ["counterparty", "document_number", "document_date", "due_date", "amount", "iban", "bic"],
    "additionalProperties": False,
}

SYSTEM = """You read finance documents for the accounts payable team of Ostrander Freight Group SA, \
the client who receives these documents and pays them. Documents are in English, French or German \
and may contain scan errors.

For every field, return the value and the quote. The quote is the exact text you read the value from, \
copied character for character as it appears in the document, including any scan errors. \
If a field is not in the document, use null for both.

Fields:
- counterparty: the company that issued the document and is to be paid. Never Ostrander Freight Group SA.
- document_number: the invoice number, payment request reference or agreement number.
- document_date: the date the document was issued or the agreement was signed, as YYYY-MM-DD. Not the date a page was scanned.
- due_date: the date payment is due, as YYYY-MM-DD. If the document gives payment terms instead of a date \
(for example "30 days net"), add that many days to the document date and quote the terms.
- amount: the amount to pay now, including VAT: the invoice total, the requested amount, or the first \
instalment of an agreement. value uses digits, a dot and two decimals (1234.56); currency is EUR or GBP.
- iban: the payee's IBAN, value without spaces.
- bic: the payee's BIC or SWIFT code.

After the document you get what simple rules found. Use it as hints only: it can be incomplete or contain noise."""


def build_messages(text: str, candidates: Candidates) -> list[dict[str, str]]:
    user = f"Document:\n<<<\n{text}\n>>>\n\nWhat simple rules found:\n{describe(candidates)}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def extract(llm: LLM, text: str, candidates: Candidates, label: str) -> Reply:
    return llm.structured(
        build_messages(text, candidates),
        schema=SCHEMA,
        validate=lambda data: validate(data, SCHEMA),
        label=label,
    )
