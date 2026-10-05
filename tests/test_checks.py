import copy

from finance_document_agent.banking import BankDirectory
from finance_document_agent.checks import References, check_document
from finance_document_agent.vendors import VendorMaster

REFS = References(
    directory=BankDirectory(
        [
            {"country": "DE", "bank_code": "37040044", "bic": "COBADEFFXXX", "name": "Example Bank Köln"},
            {"country": "DE", "bank_code": "50210900", "bic": "HNKBDEHHXXX", "name": "Hanseatische Kontorbank"},
        ]
    ),
    vendors=VendorMaster(
        [
            {
                "vendor_id": "V003",
                "name": "Hallstein Maschinenbau GmbH",
                "country": "DE",
                "iban": "DE89370400440532013000",
                "bic": "COBADEFFXXX",
            }
        ]
    ),
)

TEXT = """Hallstein Maschinenbau GmbH · Hauptstraße 12 · 20095 Hamburg

Ostrander Freight Group SA
14 Avenue de la Gare
L-1611 Luxemburg

RECHNUNG

Rechnungsnummer: RE-2026-0412
Rechnungsdatum:  04.03.2026
Fällig am: 03.04.2026

Wartung Förderanlage                       2        500,00        1.000,00

                                      Nettobetrag              1.000,00 €
                                      zzgl. 19 % USt             190,00 €
                                      Rechnungsbetrag          1.190,00 €

Bankverbindung: Example Bank Köln
IBAN: DE89 3704 0044 0532 0130 00
BIC: COBADEFFXXX
"""

GOOD = {
    "counterparty": {"value": "Hallstein Maschinenbau GmbH", "quote": "Hallstein Maschinenbau GmbH"},
    "document_number": {"value": "RE-2026-0412", "quote": "RE-2026-0412"},
    "document_date": {"value": "2026-03-04", "quote": "04.03.2026"},
    "due_date": {"value": "2026-04-03", "quote": "03.04.2026"},
    "amount": {"value": "1190.00", "currency": "EUR", "quote": "1.190,00 €"},
    "iban": {"value": "DE89370400440532013000", "quote": "DE89 3704 0044 0532 0130 00"},
    "bic": {"value": "COBADEFFXXX", "quote": "COBADEFFXXX"},
}


def run(text=TEXT, **changes):
    extraction = copy.deepcopy(GOOD)
    for field, value in changes.items():
        extraction[field] = value
    return check_document(text, extraction, REFS)


def test_a_document_that_proves_itself_is_accepted_field_by_field():
    results = run()
    assert {field: result.status for field, result in results.items()} == {field: "auto" for field in GOOD}


def test_accepted_counterparty_uses_the_vendor_master_spelling():
    results = run(counterparty={"value": "HALLSTEIN MASCHINENBAU GMBH", "quote": "Hallstein Maschinenbau GmbH"})
    assert results["counterparty"].value == "Hallstein Maschinenbau GmbH"


def test_quote_that_is_not_in_the_document_goes_to_review():
    results = run(document_number={"value": "RE-2026-0413", "quote": "RE-2026-0413"})
    assert results["document_number"].status == "review"
    assert "not found in the document" in results["document_number"].reasons[0]


def test_number_with_a_letter_between_digits_is_a_likely_scan_error():
    text = TEXT.replace("RE-2026-0412", "RE-2O26-0412")
    results = run(text, document_number={"value": "RE-2O26-0412", "quote": "RE-2O26-0412"})
    assert results["document_number"].status == "review"
    assert "scan error" in results["document_number"].reasons[0]


def test_date_that_disagrees_with_its_quote_goes_to_review():
    results = run(document_date={"value": "2026-04-03", "quote": "04.03.2026"})
    assert results["document_date"].status == "review"


def test_due_date_computed_from_payment_terms_is_accepted():
    text = TEXT.replace("Fällig am: 03.04.2026", "Zahlbar innerhalb von 30 Tagen netto")
    results = run(text, due_date={"value": "2026-04-03", "quote": "Zahlbar innerhalb von 30 Tagen netto"})
    assert results["due_date"].status == "auto"


def test_due_date_before_the_document_date_goes_to_review():
    text = TEXT.replace("Fällig am: 03.04.2026", "Fällig am: 03.02.2026")
    results = run(text, due_date={"value": "2026-02-03", "quote": "03.02.2026"})
    assert results["due_date"].status == "review"
    assert "before the document date" in results["due_date"].reasons[0]


def test_totals_that_do_not_add_up_go_to_review():
    text = TEXT.replace("Rechnungsbetrag          1.190,00 €", "Rechnungsbetrag          1.290,00 €")
    results = run(text, amount={"value": "1290.00", "currency": "EUR", "quote": "1.290,00 €"})
    assert results["amount"].status == "review"
    assert "does not add up" in results["amount"].reasons[0]


def test_two_different_totals_go_to_review():
    text = TEXT.replace(
        "Bankverbindung", "                                      Gesamtbetrag             1.200,00 €\n\nBankverbindung"
    )
    results = run(text)
    assert results["amount"].status == "review"
    assert "two different totals" in results["amount"].reasons[0]


def test_wrong_check_digits_go_to_review():
    text = TEXT.replace("DE89 3704", "DE88 3704")
    results = run(text, iban={"value": "DE88370400440532013000", "quote": "DE88 3704 0044 0532 0130 00"})
    assert results["iban"].status == "review"
    assert "check digits" in results["iban"].reasons[0]


def test_scan_error_in_the_iban_gets_a_suggested_correction_but_no_acceptance():
    text = TEXT.replace("0532 0130 00", "0532 O130 00")
    results = run(text, iban={"value": "DE89370400440532O13000", "quote": "DE89 3704 0044 0532 O130 00"})
    assert results["iban"].status == "review"
    assert results["iban"].suggestion == "DE89370400440532013000"
    assert results["iban"].value == "DE89370400440532013000"


def test_account_that_differs_from_the_vendor_master_goes_to_review():
    other = "DE37502109000000123456"  # valid check digits, at a bank in the directory
    text = TEXT.replace("DE89 3704 0044 0532 0130 00", other).replace("COBADEFFXXX", "HNKBDEHHXXX")
    results = run(text, iban={"value": other, "quote": other}, bic={"value": "HNKBDEHHXXX", "quote": "HNKBDEHHXXX"})
    assert results["iban"].status == "review"
    assert "vendor master" in results["iban"].reasons[0]


def test_bic_of_another_bank_goes_to_review():
    text = TEXT.replace("COBADEFFXXX", "HNKBDEHHXXX")
    results = run(text, bic={"value": "HNKBDEHHXXX", "quote": "HNKBDEHHXXX"})
    assert results["bic"].status == "review"
    assert "does not belong" in results["bic"].reasons[0]


def test_new_counterparty_sends_its_bank_details_to_review_too():
    text = TEXT.replace("Hallstein Maschinenbau GmbH", "Rheinfeld Logistik GmbH")
    results = run(text, counterparty={"value": "Rheinfeld Logistik GmbH", "quote": "Rheinfeld Logistik GmbH"})
    assert results["counterparty"].status == "review"
    assert "vendor master" in results["counterparty"].reasons[0]
    assert results["iban"].status == "review"
    assert results["bic"].status == "review"


def test_the_client_is_never_the_counterparty():
    results = run(counterparty={"value": "Ostrander Freight Group SA", "quote": "Ostrander Freight Group SA"})
    assert results["counterparty"].status == "review"
    assert "client" in results["counterparty"].reasons[0]


def test_missing_field_goes_to_review():
    results = run(bic={"value": None, "quote": None})
    assert results["bic"].status == "review"
    assert results["bic"].reasons == ["not found"]
