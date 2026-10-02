from decimal import Decimal

from finance_document_agent.rules import Candidates, describe, find_candidates

FRENCH = """Fournitures Vauclairon SAS
N° TVA intracommunautaire : FR27 049372052

FACTURE N° 202603-096
                                      Total HT                   25 372,37 €
                                      TVA 20 %                    5 074,47 €
                                      Total TTC                  30 446,84 €
                                      Net à payer                30 446,84 €
IBAN FR76 3078 8221 5267 6749 5440 955 - Code BIC BRVGFRPPXXX
"""


def test_iban_is_found_and_a_vat_number_is_not():
    assert find_candidates(FRENCH).ibans == ["FR7630788221526767495440955"]


def test_bic_is_found_next_to_its_label():
    assert find_candidates(FRENCH).bics == ["BRVGFRPPXXX"]


def test_bic_label_with_a_scan_error_still_works():
    assert find_candidates("SWIFT/B1C: THMBGB2L").bics == ["THMBGB2LXXX"]


def test_document_numbers_next_to_their_labels():
    assert find_candidates(FRENCH).document_numbers == ["202603-096"]
    assert find_candidates("Rechnungsnummer: RE-2026-0412").document_numbers == ["RE-2026-0412"]
    assert find_candidates("unser Zeichen ZA-2026-074").document_numbers == ["ZA-2026-074"]


def test_vat_breakdown_and_labelled_totals():
    candidates = find_candidates(FRENCH)
    assert candidates.has_vat_breakdown
    assert candidates.labelled_totals == [(Decimal("30446.84"), "EUR"), (Decimal("30446.84"), "EUR")]


def test_no_vat_breakdown_in_a_payment_request():
    assert not find_candidates("Please arrange payment of €1,250.00 by 4 March 2026.").has_vat_breakdown


def test_description_for_the_prompt_says_when_nothing_was_found():
    text = describe(Candidates())
    assert "IBAN-like strings: none found" in text
    assert "Dates: none found" in text


def test_description_shows_each_reading():
    text = describe(find_candidates(FRENCH))
    assert "30 446,84 € = 30446.84 EUR" in text.replace(" ", " ")
