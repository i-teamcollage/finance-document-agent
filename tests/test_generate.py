import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import generate  # noqa: E402

from finance_document_agent.banking import BankDirectory, iban_is_valid, normalize_iban  # noqa: E402
from finance_document_agent.vendors import VendorMaster  # noqa: E402

REFERENCE = generate.build_reference(seed=7)
DIRECTORY = BankDirectory(REFERENCE["banks"])
MASTER = VendorMaster(REFERENCE["vendors"])
DOCS = generate.build_split(seed=101, n=40, prefix="p", reference=REFERENCE)


def label(doc):
    return doc["label"]


def test_split_has_the_promised_mix():
    labels = [label(doc) for doc in DOCS]
    assert len(labels) == 40
    assert sum(item["scan"] for item in labels) == 12
    assert sum(item["trap"] is not None for item in labels) == 4
    assert sum(item["new_vendor"] for item in labels) == 2


def test_all_three_languages_and_document_types_appear():
    labels = [label(doc) for doc in DOCS]
    assert {item["language"] for item in labels} == {"en", "fr", "de"}
    assert {item["type"] for item in labels} == {"invoice", "payment_request", "contract"}


def test_same_seed_gives_the_same_documents():
    again = generate.build_split(seed=101, n=40, prefix="p", reference=generate.build_reference(seed=7))
    assert [doc["text"] for doc in again] == [doc["text"] for doc in DOCS]


def test_clean_documents_print_every_field():
    for doc in DOCS:
        if label(doc)["scan"]:
            continue
        for field, printed in label(doc)["printed"].items():
            assert printed in doc["text"], (doc["id"], field, printed)


def test_every_document_is_addressed_to_the_same_client():
    for doc in DOCS:
        assert "Ostrander Freight Group SA" in doc["text"] or "Ostrander Freight Group" in doc["text"]


def test_honest_documents_are_internally_consistent():
    for doc in DOCS:
        item = label(doc)
        if item["trap"]:
            continue
        fields = item["fields"]
        assert iban_is_valid(fields["iban"]), doc["id"]
        assert DIRECTORY.bic_matches(fields["iban"], fields["bic"]), doc["id"]
        assert date.fromisoformat(fields["due_date"]) >= date.fromisoformat(fields["document_date"]), doc["id"]
        if item.get("subtotal") is not None:
            assert Decimal(item["subtotal"]) + Decimal(item["vat"]) == Decimal(fields["amount"]["value"]), doc["id"]


def test_known_vendors_are_paid_to_their_registered_account():
    for doc in DOCS:
        item = label(doc)
        if item["new_vendor"] or item["trap"] == "vendor_bank_change":
            continue
        vendor = MASTER.match(item["fields"]["counterparty"])
        assert vendor is not None, doc["id"]
        registered = normalize_iban(vendor["iban"])
        if item["trap"] == "iban_checksum":  # same account, deliberately wrong check digits
            assert registered[4:] == item["fields"]["iban"][4:], doc["id"]
        else:
            assert registered == item["fields"]["iban"], doc["id"]


def test_new_vendors_are_not_in_the_vendor_master():
    for doc in DOCS:
        if label(doc)["new_vendor"]:
            assert MASTER.match(label(doc)["fields"]["counterparty"]) is None, doc["id"]


def test_each_trap_really_is_broken():
    traps = {}
    for doc in generate.build_split(seed=202, n=80, prefix="t", reference=REFERENCE):
        item = label(doc)
        if not item["trap"]:
            continue
        traps.setdefault(item["trap"], []).append(item)
    assert set(traps) == {"iban_checksum", "vendor_bank_change", "bic_mismatch", "total_mismatch", "due_before_issue"}
    for item in traps["iban_checksum"]:
        assert not iban_is_valid(item["fields"]["iban"])
    for item in traps["vendor_bank_change"]:
        vendor = MASTER.match(item["fields"]["counterparty"])
        assert iban_is_valid(item["fields"]["iban"])
        assert normalize_iban(vendor["iban"]) != item["fields"]["iban"]
    for item in traps["bic_mismatch"]:
        assert not DIRECTORY.bic_matches(item["fields"]["iban"], item["fields"]["bic"])
    for item in traps["total_mismatch"]:
        assert Decimal(item["subtotal"]) + Decimal(item["vat"]) != Decimal(item["fields"]["amount"]["value"])
    for item in traps["due_before_issue"]:
        assert item["fields"]["due_date"] < item["fields"]["document_date"]


def test_trap_names_the_field_a_reviewer_must_look_at():
    for doc in generate.build_split(seed=202, n=80, prefix="t", reference=REFERENCE):
        item = label(doc)
        if item["trap"]:
            assert item["review_field"] in item["fields"], doc["id"]


def test_scanned_documents_differ_from_their_clean_version():
    scanned = [doc for doc in DOCS if label(doc)["scan"]]
    assert all(doc["text"] != doc["clean_text"] for doc in scanned)
