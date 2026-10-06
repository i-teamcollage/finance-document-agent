"""The confidence line: a field is accepted automatically only when the code can prove it.

Every check here is something a reviewer could verify by hand: the quote is really in the document,
the date in the quote is the date reported, the IBAN's check digits work, the bank exists, the account
is the one in the vendor master, the totals add up. Anything unproven goes to a person, with a reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .banking import BankDirectory, bic11, bic_format_ok, iban_is_valid, normalize_iban, repair_iban
from .parsing import days_from_terms, find_amounts, find_dates, parse_amount, parse_date
from .rules import Candidates, find_candidates
from .vendors import VendorMaster, normalize_name

CLIENT = "Ostrander Freight Group SA"
FIELDS = ("counterparty", "document_number", "document_date", "due_date", "amount", "iban", "bic")


@dataclass
class References:
    directory: BankDirectory
    vendors: VendorMaster


@dataclass
class FieldResult:
    field: str
    value: Any
    status: str  # "auto" or "review"
    reasons: list[str] = field(default_factory=list)
    quote: str | None = None
    suggestion: str | None = None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ").replace("\u202f", " ")).strip()


def _quote_found(quote: str | None, text: str) -> bool:
    return bool(quote) and _squash(quote) in _squash(text)


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _date_in(quote: str) -> date | None:
    whole = parse_date(quote)
    if whole:
        return whole
    found = find_dates(quote)
    return found[0][1] if len(found) == 1 else None


class _Field:
    def __init__(self, name: str, item: dict[str, Any]):
        self.name, self.item = name, item
        self.reasons: list[str] = []

    def problem(self, reason: str) -> None:
        self.reasons.append(reason)

    def result(self, value: Any, suggestion: str | None = None) -> FieldResult:
        status = "review" if self.reasons else "auto"
        return FieldResult(self.name, value, status, self.reasons, self.item.get("quote"), suggestion)


def check_document(text: str, extraction: dict[str, dict[str, Any]], refs: References) -> dict[str, FieldResult]:
    candidates = find_candidates(text)
    results: dict[str, FieldResult] = {}
    results["counterparty"], vendor = _counterparty(text, extraction["counterparty"], refs)
    results["document_number"] = _document_number(text, extraction["document_number"], candidates)
    results["document_date"] = _document_date(text, extraction["document_date"])
    results["due_date"] = _due_date(text, extraction["due_date"], _iso(results["document_date"].value))
    results["amount"] = _amount(text, extraction["amount"], candidates)
    new_counterparty = vendor is None
    results["iban"] = _iban(text, extraction["iban"], candidates, refs, vendor, new_counterparty)
    results["bic"] = _bic(text, extraction["bic"], candidates, refs, results["iban"].value, new_counterparty)
    return results


def unreadable(reason: str) -> dict[str, FieldResult]:
    """Every field goes to a person when the model's answer could not be used at all."""
    return {name: FieldResult(name, None, "review", [reason]) for name in FIELDS}


def _missing(name: str, item: dict[str, Any]) -> FieldResult | None:
    if item.get("value") in (None, ""):
        return FieldResult(name, None, "review", ["not found"], item.get("quote"))
    return None


def _counterparty(text: str, item: dict[str, Any], refs: References) -> tuple[FieldResult, dict | None]:
    missing = _missing("counterparty", item)
    if missing:
        return missing, None
    check = _Field("counterparty", item)
    value = item["value"]
    if normalize_name(value) == normalize_name(CLIENT):
        check.problem("this is the client who pays, not the counterparty")
        return check.result(value), None
    if not _quote_found(item.get("quote"), text):
        check.problem("quote not found in the document")
    vendor = refs.vendors.match(value) or refs.vendors.match(item.get("quote") or "")
    if vendor is None:
        check.problem("not in the vendor master: new counterparty, needs onboarding")
        return check.result(value), None
    return check.result(vendor["name"]), vendor


def _document_number(text: str, item: dict[str, Any], candidates: Candidates) -> FieldResult:
    missing = _missing("document_number", item)
    if missing:
        return missing
    check = _Field("document_number", item)
    value = item["value"].strip()
    compact = re.sub(r"\s+", "", value)
    labelled = [re.sub(r"\s+", "", c) for c in candidates.document_numbers]
    quoted = _quote_found(item.get("quote"), text) and compact in re.sub(r"\s+", "", item.get("quote") or "")
    # A reworded label in the quote is fine when the rules found exactly this number next to its label.
    if not quoted and compact not in labelled:
        check.problem("quote not found in the document")
    elif re.search(r"\d[OolISBZ]|[OolISBZ]\d", compact):
        check.problem("a letter between digits: likely scan error")
    elif not re.search(r"\d", compact) or not 3 <= len(compact) <= 30:
        check.problem("does not look like a document number")
    elif labelled and compact not in labelled:
        check.problem("differs from the number printed next to its label")
    return check.result(value)


def _document_date(text: str, item: dict[str, Any]) -> FieldResult:
    missing = _missing("document_date", item)
    if missing:
        return missing
    check = _Field("document_date", item)
    value = _iso(item["value"])
    if value is None:
        check.problem("not a valid date")
        return check.result(item["value"])
    if not _quote_found(item.get("quote"), text):
        check.problem("quote not found in the document")
    else:
        quoted = _date_in(item["quote"])
        if quoted != value:
            check.problem(f"the quoted text reads {quoted.isoformat() if quoted else 'no single date'}")
    return check.result(value.isoformat())


def _due_date(text: str, item: dict[str, Any], issued: date | None) -> FieldResult:
    missing = _missing("due_date", item)
    if missing:
        return missing
    check = _Field("due_date", item)
    value = _iso(item["value"])
    if value is None:
        check.problem("not a valid date")
        return check.result(item["value"])
    if not _quote_found(item.get("quote"), text):
        check.problem("quote not found in the document")
    else:
        quoted = _date_in(item["quote"])
        days = days_from_terms(item["quote"])
        if quoted is not None:
            if quoted != value:
                check.problem(f"the quoted text reads {quoted.isoformat()}")
        elif days is not None and issued is not None:
            if issued + timedelta(days=days) != value:
                check.problem(f"{days} days after the document date is {(issued + timedelta(days=days)).isoformat()}")
        else:
            check.problem("no date or payment terms in the quote")
    if issued is not None and value < issued:
        check.reasons.insert(0, "due date before the document date")
    return check.result(value.isoformat())


def _amount(text: str, item: dict[str, Any], candidates: Candidates) -> FieldResult:
    missing = _missing("amount", item)
    if missing:
        return FieldResult("amount", None, "review", ["not found"], item.get("quote"))
    check = _Field("amount", item)
    currency = item.get("currency")
    # "8511.31 EUR" is the right amount in the wrong format: keep the number, but only if the code matches.
    written = re.fullmatch(r"\s*(€|EUR|£|GBP)?\s*(\d+\.\d{2})\s*(€|EUR|£|GBP)?\s*", str(item["value"]))
    codes = {"€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}
    if written is None or any(code and codes[code] != currency for code in (written.group(1), written.group(3))):
        check.problem("not a valid amount")
        return check.result({"value": item["value"], "currency": currency})
    value = Decimal(written.group(2))
    reported = {"value": f"{value:.2f}", "currency": currency}
    distinct_totals = {(total, cur) for total, cur in candidates.labelled_totals}
    if len(distinct_totals) > 1:
        check.problem("two different totals in the document")
    if not _quote_found(item.get("quote"), text):
        check.problem("quote not found in the document")
    else:
        # The quote may be a whole sentence with several amounts; the reported one must be among them.
        in_quote = [(v, c) for _, v, c in find_amounts(item["quote"])]
        whole = parse_amount(item["quote"])
        if whole:
            in_quote.append(whole)
        if (value, currency) not in in_quote:
            first = in_quote[0] if in_quote else None
            check.problem(f"the quoted text reads {first[0]} {first[1]}" if first else "no amount in the quote")
    if candidates.has_vat_breakdown:
        amounts = [v for _, v, c in candidates.amounts if c == currency]
        if not any(a + b == value for i, a in enumerate(amounts) for b in amounts[i + 1 :]):
            check.problem("net amount + VAT does not add up to this total")
    return check.result(reported)


def _iban(
    text: str,
    item: dict[str, Any],
    candidates: Candidates,
    refs: References,
    vendor: dict | None,
    new_counterparty: bool,
) -> FieldResult:
    missing = _missing("iban", item)
    if missing:
        return missing
    check = _Field("iban", item)
    value = normalize_iban(item["value"])
    suggestion = None
    if not _quote_found(item.get("quote"), text) or value not in normalize_iban(item.get("quote") or ""):
        check.problem("quote not found in the document")
    if not iban_is_valid(value):
        repairs = repair_iban(value, refs.directory)
        if len(repairs) == 1:
            suggestion = repairs[0]
            check.reasons.insert(0, f"IBAN check digits fail: likely scan error, suggested correction {suggestion}")
        else:
            check.reasons.insert(0, "IBAN check digits fail")
        return check.result(suggestion or value, suggestion)
    if candidates.ibans and value not in candidates.ibans:
        check.problem("the rules did not find this IBAN in the document")
    if refs.directory.bic_for(value) is None:
        check.problem("bank not in the bank directory")
    if vendor is not None and normalize_iban(vendor["iban"]) != value:
        check.reasons.insert(
            0, "differs from the account in the vendor master: possible payment diversion, confirm by phone"
        )
    elif new_counterparty:
        check.problem("new counterparty: bank details not verified")
    return check.result(value)


def _bic(
    text: str,
    item: dict[str, Any],
    candidates: Candidates,
    refs: References,
    iban: str | None,
    new_counterparty: bool,
) -> FieldResult:
    missing = _missing("bic", item)
    if missing:
        return missing
    check = _Field("bic", item)
    if not bic_format_ok(item["value"]):
        check.problem("not a valid BIC format")
        return check.result(item["value"])
    value = bic11(item["value"])
    if not _quote_found(item.get("quote"), text):
        check.problem("quote not found in the document")
    if iban and iban_is_valid(iban) and not refs.directory.bic_matches(iban, value):
        check.reasons.insert(0, "does not belong to the IBAN's bank in the directory")
    elif not iban or not iban_is_valid(iban):
        check.problem("cannot be checked without a valid IBAN")
    if candidates.bics and value not in candidates.bics:
        check.problem("differs from the BIC printed next to its label")
    if new_counterparty:
        check.problem("new counterparty: bank details not verified")
    return check.result(value)
