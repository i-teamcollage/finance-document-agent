"""Score the agent's decisions against the answer key, using the rules in the spec."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .acceptance import Measure, rate
from .banking import bic11, normalize_iban
from .checks import FIELDS
from .pipeline import DocumentResult
from .vendors import normalize_name

BANK_FIELDS = ("iban", "bic")


def field_correct(field: str, value: Any, truth: Any) -> bool:
    if value in (None, "") or truth in (None, ""):
        return False
    if field == "counterparty":
        return normalize_name(value) == normalize_name(truth)
    if field == "document_number":
        return re.sub(r"\s+", "", value).upper() == re.sub(r"\s+", "", truth).upper()
    if field == "amount":
        try:
            return Decimal(value["value"]) == Decimal(truth["value"]) and value["currency"] == truth["currency"]
        except (InvalidOperation, TypeError, KeyError):
            return False
    if field == "iban":
        return normalize_iban(value) == normalize_iban(truth)
    if field == "bic":
        return bic11(value) == bic11(truth)
    return value == truth


def score(labels: list[dict], results: dict[str, DocumentResult]) -> tuple[dict[str, Measure], str]:
    auto = {"all": [0, 0], "bank": [0, 0]}
    found, fields_total = 0, 0
    per_field = {name: {"auto": 0, "auto_correct": 0, "found": 0, "total": 0} for name in FIELDS}
    straight, traps_caught, traps = 0, 0, 0
    wrong_accepts, trap_lines = [], []

    for label in labels:
        result = results[label["id"]]
        straight += result.straight_through
        for name in FIELDS:
            outcome, truth = result.fields[name], label["fields"][name]
            correct = field_correct(name, outcome.value, truth)
            fields_total += 1
            found += correct
            per_field[name]["total"] += 1
            per_field[name]["found"] += correct
            if outcome.status == "auto":
                per_field[name]["auto"] += 1
                per_field[name]["auto_correct"] += correct
                auto["all"][0] += correct
                auto["all"][1] += 1
                if name in BANK_FIELDS:
                    auto["bank"][0] += correct
                    auto["bank"][1] += 1
                if not correct:
                    wrong_accepts.append(f"{label['id']} {name}: accepted {outcome.value!r}, answer key {truth!r}")
        if label.get("trap"):
            traps += 1
            caught = result.fields[label["review_field"]].status == "review"
            traps_caught += caught
            trap_lines.append(f"{label['id']} {label['trap']}: {'sent to review' if caught else 'MISSED'}")

    measures = {
        "bank_auto_precision": rate(*auto["bank"]),
        "field_auto_precision": rate(*auto["all"]),
        "field_recall": rate(found, fields_total),
        "straight_through": rate(straight, len(labels)),
        "trap_review": rate(traps_caught, traps),
    }
    return measures, _details(per_field, wrong_accepts, trap_lines)


def _percent(hits: int, total: int) -> str:
    return f"{hits / total * 100:.1f}%" if total else "n/a"


def _details(per_field: dict, wrong_accepts: list[str], trap_lines: list[str]) -> str:
    lines = [
        "## Per field",
        "",
        "| Field | Accepted automatically | Correct when accepted | Found (accepted or in review) |",
        "|---|---|---|---|",
    ]
    for name, row in per_field.items():
        lines.append(
            f"| {name} | {_percent(row['auto'], row['total'])} | {_percent(row['auto_correct'], row['auto'])} "
            f"| {_percent(row['found'], row['total'])} |"
        )
    lines += ["", "## Wrong values that were accepted automatically", ""]
    lines += [f"- {line}" for line in wrong_accepts] or ["None."]
    lines += ["", "## Trap documents", ""]
    lines += [f"- {line}" for line in trap_lines] or ["None in this split."]
    return "\n".join(lines)
