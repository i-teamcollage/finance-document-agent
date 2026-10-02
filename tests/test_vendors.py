from finance_document_agent.vendors import VendorMaster, normalize_name

MASTER = VendorMaster(
    [
        {"vendor_id": "V001", "name": "Brightmoor Logistics Ltd", "country": "GB", "iban": "GB29NWBK60161331926819", "bic": "NWBKGB2LXXX"},
        {"vendor_id": "V002", "name": "Société Lumière Rivage SAS", "country": "FR", "iban": "FR1420041010050500013M02606", "bic": "PSSTFRPPXXX"},
        {"vendor_id": "V003", "name": "Hallstein Maschinenbau GmbH", "country": "DE", "iban": "DE89370400440532013000", "bic": "COBADEFFXXX"},
    ]
)


def test_legal_forms_case_and_punctuation_do_not_matter():
    assert normalize_name("Brightmoor Logistics Ltd.") == "brightmoor logistics"
    assert normalize_name("BRIGHTMOOR LOGISTICS LIMITED") == "brightmoor logistics"


def test_accents_and_compound_legal_forms_are_removed():
    assert normalize_name("Société Lumière Rivage S.A.S.") == "societe lumiere rivage"
    assert normalize_name("Hallstein Maschinenbau GmbH & Co. KG") == "hallstein maschinenbau"


def test_exact_name_matches_the_vendor():
    assert MASTER.match("Hallstein Maschinenbau GmbH")["vendor_id"] == "V003"


def test_name_with_a_scan_error_still_matches():
    assert MASTER.match("Br1ghtmoor Logistics Ltd")["vendor_id"] == "V001"


def test_unknown_company_does_not_match():
    assert MASTER.match("Completely Different Trading SARL") is None


def test_similar_but_different_company_does_not_match():
    assert MASTER.match("Brightmoor Catering Ltd") is None


def test_empty_name_does_not_match():
    assert MASTER.match("") is None
