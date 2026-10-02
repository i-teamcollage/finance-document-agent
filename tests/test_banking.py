from finance_document_agent.banking import (
    BankDirectory,
    bank_code,
    bic11,
    bic_format_ok,
    iban_is_valid,
    make_iban,
    normalize_iban,
    repair_iban,
)

# Standard documentation examples, not real accounts of anyone in this repo.
DE = "DE89370400440532013000"
FR = "FR1420041010050500013M02606"
GB = "GB29NWBK60161331926819"

DIRECTORY = BankDirectory(
    [
        {"country": "DE", "bank_code": "37040044", "bic": "COBADEFFXXX", "name": "Example Bank Köln"},
        {"country": "GB", "bank_code": "NWBK", "bic": "NWBKGB2LXXX", "name": "Example Bank London"},
    ]
)


def test_normalize_iban_removes_spaces_and_uppercases():
    assert normalize_iban(" de89 3704 0044 0532 0130 00 ") == DE


def test_valid_iban_passes():
    assert iban_is_valid(DE) and iban_is_valid(FR) and iban_is_valid(GB)


def test_one_wrong_digit_fails_the_check_digits():
    assert not iban_is_valid("DE89370400440532013001")


def test_wrong_length_for_the_country_fails():
    assert not iban_is_valid("DE8937040044053201300")


def test_unknown_country_fails():
    assert not iban_is_valid("XX89370400440532013000")


def test_make_iban_computes_the_check_digits():
    assert make_iban("DE", "370400440532013000") == DE
    assert make_iban("FR", "20041010050500013M02606") == FR


def test_bank_code_depends_on_the_country():
    assert bank_code(DE) == "37040044"
    assert bank_code(FR) == "20041"
    assert bank_code(GB) == "NWBK"


def test_bank_code_of_an_unsupported_country_is_none():
    assert bank_code("NO9386011117947") is None


def test_bic_format():
    assert bic_format_ok("COBADEFFXXX")
    assert bic_format_ok("COBADEFF")
    assert not bic_format_ok("COBADE")
    assert not bic_format_ok("C0BADEFF")


def test_bic11_pads_the_branch_code():
    assert bic11("COBADEFF") == "COBADEFFXXX"
    assert bic11("coba deff xxx") == "COBADEFFXXX"


def test_directory_finds_the_bic_for_an_iban():
    assert DIRECTORY.bic_for(DE) == "COBADEFFXXX"


def test_directory_treats_8_and_11_character_bics_as_equal():
    assert DIRECTORY.bic_matches(DE, "COBADEFF")
    assert not DIRECTORY.bic_matches(DE, "NWBKGB2L")


def test_directory_knows_nothing_about_unlisted_banks():
    assert DIRECTORY.bic_for(FR) is None
    assert not DIRECTORY.bic_matches(FR, "BNPAFRPP")


def test_scan_error_is_repaired_by_check_digits_and_directory():
    assert repair_iban("DE89370400440532O13000", DIRECTORY) == [DE]


def test_repair_handles_letters_read_as_digits_too():
    assert repair_iban("GB29NW8K60161331926819", DIRECTORY) == [GB]


def test_nothing_to_repair_in_a_valid_iban():
    assert repair_iban(DE, DIRECTORY) == []


def test_unrepairable_iban_gives_no_suggestion():
    assert repair_iban("DE00370400440532013000", DIRECTORY) == []
