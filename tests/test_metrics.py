from finance_document_agent.checks import FieldResult
from finance_document_agent.metrics import field_correct, score
from finance_document_agent.pipeline import DocumentResult

TRUTH = {
    "counterparty": "Hallstein Maschinenbau GmbH",
    "document_number": "RE-2026-0412",
    "document_date": "2026-03-04",
    "due_date": "2026-04-03",
    "amount": {"value": "1190.00", "currency": "EUR"},
    "iban": "DE89370400440532013000",
    "bic": "COBADEFFXXX",
}


def label(doc_id, trap=None, review_field=None):
    return {"id": doc_id, "fields": TRUTH, "trap": trap, "review_field": review_field}


def result(doc_id, statuses=None, values=None):
    statuses, values = statuses or {}, values or {}
    fields = {
        name: FieldResult(name, values.get(name, TRUTH[name]), statuses.get(name, "auto")) for name in TRUTH
    }
    return DocumentResult(doc_id, fields, all(f.status == "auto" for f in fields.values()), 10.0)


def test_names_are_compared_without_legal_form_or_case():
    assert field_correct("counterparty", "HALLSTEIN MASCHINENBAU", "Hallstein Maschinenbau GmbH")


def test_amounts_must_match_value_and_currency():
    assert field_correct("amount", {"value": "1190.00", "currency": "EUR"}, TRUTH["amount"])
    assert not field_correct("amount", {"value": "1190.00", "currency": "GBP"}, TRUTH["amount"])


def test_eight_character_bic_equals_its_branch_form():
    assert field_correct("bic", "COBADEFFXXX", "COBADEFF")


def test_document_numbers_ignore_spaces_and_case():
    assert field_correct("document_number", "re-2026 -0412", "RE-2026-0412")


def test_missing_value_is_never_correct():
    assert not field_correct("iban", None, TRUTH["iban"])


def test_perfect_run_scores_full_marks():
    measures, _ = score([label("a"), label("b")], {"a": result("a"), "b": result("b")})
    assert measures["bank_auto_precision"].value == 1.0
    assert measures["field_recall"].value == 1.0
    assert measures["straight_through"].value == 1.0


def test_a_wrong_accepted_iban_lowers_bank_precision():
    wrong = result("a", values={"iban": "DE37502109000000123456"})
    measures, details = score([label("a")], {"a": wrong})
    assert measures["bank_auto_precision"].hits == 1
    assert measures["bank_auto_precision"].total == 2
    assert "DE37502109000000123456" in details


def test_a_field_sent_to_review_counts_for_recall_but_not_for_precision():
    reviewed = result("a", statuses={"iban": "review"})
    measures, _ = score([label("a")], {"a": reviewed})
    assert measures["bank_auto_precision"].total == 1
    assert measures["field_recall"].value == 1.0
    assert measures["straight_through"].value == 0.0


def test_trap_counts_only_when_its_own_field_was_sent_to_review():
    caught = result("a", statuses={"iban": "review"})
    missed = result("b", statuses={"amount": "review"})
    labels = [label("a", "iban_checksum", "iban"), label("b", "vendor_bank_change", "iban")]
    measures, _ = score(labels, {"a": caught, "b": missed})
    assert (measures["trap_review"].hits, measures["trap_review"].total) == (1, 2)
