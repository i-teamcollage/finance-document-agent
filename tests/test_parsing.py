from datetime import date
from decimal import Decimal

from finance_document_agent.parsing import days_from_terms, find_amounts, find_dates, parse_amount, parse_date

MARCH_4 = date(2026, 3, 4)


def test_iso_date():
    assert parse_date("2026-03-04") == MARCH_4


def test_numeric_dates_are_day_first_as_in_europe():
    assert parse_date("04/03/2026") == MARCH_4
    assert parse_date("04.03.2026") == MARCH_4


def test_english_dates_in_words():
    assert parse_date("4 March 2026") == MARCH_4
    assert parse_date("4th March 2026") == MARCH_4
    assert parse_date("March 4, 2026") == MARCH_4


def test_french_dates_in_words():
    assert parse_date("4 mars 2026") == MARCH_4
    assert parse_date("1er avril 2026") == date(2026, 4, 1)
    assert parse_date("17 février 2026") == date(2026, 2, 17)


def test_german_dates_in_words():
    assert parse_date("4. März 2026") == MARCH_4
    assert parse_date("17. Februar 2026") == date(2026, 2, 17)


def test_scan_errors_inside_numbers_are_fixed():
    assert parse_date("2O26-03-04") == MARCH_4
    assert parse_date("l5.03.2026") == date(2026, 3, 15)


def test_scan_errors_in_dates_written_in_words_are_fixed_too():
    assert parse_date("4. März 2O26") == MARCH_4
    assert parse_date("l5 March 2026") == date(2026, 3, 15)
    assert parse_date("March 4, 2O26") == MARCH_4


def test_impossible_dates_are_rejected():
    assert parse_date("31/02/2026") is None
    assert parse_date("not a date") is None


def test_find_dates_returns_quotes_in_order():
    found = find_dates("Invoice date: 04.03.2026   Due: 03.04.2026")
    assert found == [("04.03.2026", MARCH_4), ("03.04.2026", date(2026, 4, 3))]


def test_find_dates_reads_words_too():
    assert find_dates("Fait le 4 mars 2026 à Lyon") == [("4 mars 2026", MARCH_4)]


def test_german_amount():
    assert parse_amount("1.234,56 €") == (Decimal("1234.56"), "EUR")


def test_english_amount():
    assert parse_amount("€1,234.56") == (Decimal("1234.56"), "EUR")


def test_french_amount_with_a_narrow_space():
    assert parse_amount("12\u202f345,67 EUR") == (Decimal("12345.67"), "EUR")


def test_pounds():
    assert parse_amount("£980.00") == (Decimal("980.00"), "GBP")


def test_currency_code_before_the_number():
    assert parse_amount("EUR 1.234,56") == (Decimal("1234.56"), "EUR")


def test_scan_error_inside_an_amount_is_fixed():
    assert parse_amount("1.2S4,56 €") == (Decimal("1254.56"), "EUR")


def test_amount_without_a_currency_is_not_an_amount():
    assert parse_amount("12.50") is None


def test_find_amounts_returns_every_amount_in_order():
    found = find_amounts("Subtotal: €1,000.00  VAT 19%: €190.00  Total: €1,190.00")
    assert [(value, currency) for _, value, currency in found] == [
        (Decimal("1000.00"), "EUR"),
        (Decimal("190.00"), "EUR"),
        (Decimal("1190.00"), "EUR"),
    ]
    assert found[2][0] == "€1,190.00"


def test_payment_terms_in_three_languages():
    assert days_from_terms("Payment terms: 30 days net") == 30
    assert days_from_terms("Net 60") == 60
    assert days_from_terms("Zahlbar innerhalb von 14 Tagen netto") == 14
    assert days_from_terms("Paiement à 45 jours") == 45
    assert days_from_terms("no terms here") is None


def test_payment_terms_survive_scan_errors_in_the_number():
    assert days_from_terms("Zahlbar innerhalb von l4 Tagen netto") == 14
    assert days_from_terms("3O days net") == 30
