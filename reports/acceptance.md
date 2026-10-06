# Finance document agent: acceptance test

| Criterion | Target | Measured | 95% interval | Result |
|---|---|---|---|---|
| Bank details accepted automatically that are correct | ≥ 99% | 100.0% | 97.2–100.0% | PASS |
| All fields accepted automatically that are correct | ≥ 98% | 100.0% | 99.3–100.0% | PASS |
| Fields found correctly, whether accepted or sent to review | ≥ 95% | 98.9% | 97.7–99.5% | PASS |
| Documents fully processed with no human touch | ≥ 70% | 70.0% | 59.2–78.9% | PASS |
| Trap documents sent to review | = 100% | 100.0% | 67.6–100.0% | PASS |

80 made-up test cases, ministral-3:8b on Apple M4, 16 GB, recorded 2026-10-06, median 28.2 s per item.

All criteria passed.

## Per field

| Field | Accepted automatically | Correct when accepted | Found (accepted or in review) |
|---|---|---|---|
| counterparty | 95.0% | 100.0% | 100.0% |
| document_number | 98.8% | 100.0% | 98.8% |
| document_date | 100.0% | 100.0% | 100.0% |
| due_date | 95.0% | 100.0% | 96.2% |
| amount | 97.5% | 100.0% | 100.0% |
| iban | 78.8% | 100.0% | 100.0% |
| bic | 87.5% | 100.0% | 97.5% |

## Wrong values that were accepted automatically

None.

## Trap documents

- t-028 bic_mismatch: sent to review
- t-030 iban_checksum: sent to review
- t-035 iban_checksum: sent to review
- t-036 total_mismatch: sent to review
- t-044 vendor_bank_change: sent to review
- t-050 bic_mismatch: sent to review
- t-058 vendor_bank_change: sent to review
- t-076 due_before_issue: sent to review
