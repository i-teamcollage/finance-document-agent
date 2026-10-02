"""Generate the made-up finance documents, their labels, the vendor master and the bank directory.

    python data/generate.py           write everything under data/
    python data/generate.py --check   regenerate in memory and compare with the committed files

Fixed seeds, the repo's own word lists, no Faker: the output never changes unless this file does.
Every company, bank, person and account number is fictional. The IBANs have valid check digits
for a fictional bank directory; they are not real accounts.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from templates import BANK_CHANGE_NOTICE, TEMPLATES, TERMS, fmt_amount, fmt_date, fmt_iban, fmt_number  # noqa: E402
from words import (  # noqa: E402
    ADDRESSES,
    BANKS,
    CURRENCY,
    LANGUAGE_OF_COUNTRY,
    LINE_ITEMS,
    NAME_PARTS,
    PEOPLE,
    VAT_RATES,
)

from finance_document_agent.banking import bic11, make_iban  # noqa: E402
from finance_document_agent.vendors import normalize_name  # noqa: E402

REFERENCE_SEED = 7
SPLITS = {"practice": (101, 40, "p"), "test": (202, 80, "t")}
SCAN_SHARE, TRAP_SHARE, NEW_VENDOR_SHARE = 0.30, 0.10, 0.05
OCR_RATE = 0.02
TRAP_TYPES = ["iban_checksum", "vendor_bank_change", "bic_mismatch", "total_mismatch", "due_before_issue"]
TRAP_FIELD = {
    "iban_checksum": "iban",
    "vendor_bank_change": "iban",
    "bic_mismatch": "bic",
    "total_mismatch": "amount",
    "due_before_issue": "due_date",
}
VENDOR_COUNTRIES = {"en": [("GB", 6), ("IE", 4), ("NL", 5)], "fr": [("FR", 10), ("BE", 5)], "de": [("DE", 10), ("AT", 5)]}
OCR_CONFUSIONS = {"0": "O", "O": "0", "1": "l", "l": "1", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2"}
CENT = Decimal("0.01")


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(n))


def _letters(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXY") for _ in range(n))


def make_bban(country: str, bank_code: str, rng: random.Random) -> str:
    if country == "DE":
        return bank_code + _digits(rng, 10)
    if country == "AT":
        return bank_code + _digits(rng, 11)
    if country == "FR":
        branch, account = _digits(rng, 5), _digits(rng, 11)
        key = 97 - ((89 * int(bank_code) + 15 * int(branch) + 3 * int(account)) % 97)
        return f"{bank_code}{branch}{account}{key:02d}"
    if country == "BE":
        first_ten = bank_code + _digits(rng, 7)
        return f"{first_ten}{int(first_ten) % 97 or 97:02d}"
    if country == "NL":
        return bank_code + _digits(rng, 10)
    return bank_code + _digits(rng, 6) + _digits(rng, 8)  # GB and IE: bank, sort code, account


def _postcode_line(country: str, city: str, rng: random.Random) -> str:
    if country == "GB":
        return f"{city} {_letters(rng, 2)}{rng.randint(1, 19)} {rng.randint(1, 9)}{_letters(rng, 2)}"
    if country == "IE":
        return f"{city}, Ireland"
    if country == "NL":
        return f"{rng.randint(1000, 9999)} {_letters(rng, 2)} {city}"
    if country in ("FR", "DE"):
        return f"{rng.randint(10000, 99999)} {city}"
    return f"{rng.randint(1000, 9999)} {city}"


def _vat_id(country: str, rng: random.Random) -> str:
    return {
        "GB": f"GB {_digits(rng, 3)} {_digits(rng, 4)} {_digits(rng, 2)}",
        "IE": f"IE{_digits(rng, 7)}{_letters(rng, 1)}",
        "NL": f"NL{_digits(rng, 9)}B01",
        "FR": f"FR{_digits(rng, 2)} {_digits(rng, 9)}",
        "BE": f"BE0{_digits(rng, 9)}",
        "DE": f"DE{_digits(rng, 9)}",
        "AT": f"ATU{_digits(rng, 8)}",
    }[country]


def make_vendor(rng: random.Random, lang: str, country: str, banks: list[dict], taken: list[str]) -> dict:
    parts = NAME_PARTS[lang]
    while True:
        first, sector = rng.choice(parts["first"]), rng.choice(parts["sector"])
        legal = rng.choice(parts["legal"][country])
        name = f"{sector} {first} {legal}" if lang == "fr" else f"{first} {sector} {legal}"
        normalized = normalize_name(name)
        if all(SequenceMatcher(None, normalized, other).ratio() < 0.9 for other in taken):
            break
    taken.append(normalized)
    streets, cities = ADDRESSES[country]
    street, city = rng.choice(streets), rng.choice(cities)
    number = rng.randint(2, 180)
    street_line = f"{street} {number}" if country in ("DE", "AT", "NL") else f"{number} {street}"
    bank = rng.choice([b for b in banks if b["country"] == country])
    return {
        "name": name,
        "country": country,
        "street": street_line,
        "city": city,
        "city_line": _postcode_line(country, city, rng),
        "vat_id": _vat_id(country, rng),
        "iban": make_iban(country, make_bban(country, bank["bank_code"], rng)),
        "bic": bank["bic"],
    }


def build_reference(seed: int = REFERENCE_SEED) -> dict:
    rng = random.Random(seed)
    banks = [{"country": c, "bank_code": code, "bic": bic, "name": name} for c, code, bic, name in BANKS]
    vendors, taken = [], []
    for lang, countries in VENDOR_COUNTRIES.items():
        for country, count in countries:
            for _ in range(count):
                vendors.append(make_vendor(rng, lang, country, banks, taken))
    for number, vendor in enumerate(vendors, start=1):
        vendor["vendor_id"] = f"V{number:03d}"
    return {"banks": banks, "vendors": vendors, "taken": taken}


def _doc_number(rng: random.Random, lang: str, kind: str, issued: date) -> str:
    y, yy, mm, n = issued.year, issued.year % 100, issued.month, rng.randint(1, 9999)
    if kind == "payment_request":
        return {"en": f"PR-{y}-{n % 1000:03d}", "fr": f"DR-{y}-{n % 1000:03d}", "de": f"ZA-{y}-{n % 1000:03d}"}[lang]
    if kind == "contract":
        return {"en": f"SA-{y}-{n % 1000:03d}", "fr": f"CT-{y}-{n % 1000:03d}", "de": f"V-{yy}-{n:04d}"}[lang]
    choices = {
        "en": [f"INV-{y}-{n:05d}", f"SI/{yy}/{n:05d}", str(rng.randint(100000, 999999)), f"INV{yy}{n:04d}"],
        "fr": [f"F{y}-{n:04d}", f"FA-{yy}-{n:04d}", f"{y}{mm:02d}-{n % 1000:03d}"],
        "de": [f"RE-{y}-{n:04d}", f"{y}/{mm:02d}/{n:04d}", f"R{yy}{n:05d}"],
    }[lang]
    return rng.choice(choices)


def scan_noise(text: str, issued: date, lang: str, rng: random.Random) -> str:
    """What a cheap scanner and OCR do to a page: misread characters, merged columns, stray marks."""
    chars = [OCR_CONFUSIONS[ch] if ch in OCR_CONFUSIONS and rng.random() < OCR_RATE else ch for ch in text]
    lines = "".join(chars).split("\n")
    lines = [re.sub(r" {2,}", " ", line) if rng.random() < 0.3 else line for line in lines]
    filled = [index for index, line in enumerate(lines) if line.strip()]
    for index in rng.sample(filled, k=min(3, len(filled))):
        lines[index] += rng.choice([" '", " `", " ·", " ,"])
    scanned = issued + timedelta(days=rng.randint(2, 20))
    header = {"en": "Scanned", "fr": "Numérisé le", "de": "Gescannt am"}[lang]
    return f"{header} {fmt_date(scanned, lang, 0)} {rng.randint(7, 18):02d}:{rng.randint(0, 59):02d}  p.1/1\n" + "\n".join(lines) + "\n- 1 -\n"


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def make_document(rng: random.Random, doc_id: str, lang: str, kind: str, vendor: dict, plan: dict, reference: dict) -> dict:
    banks = reference["banks"]
    country = vendor["country"]
    currency = CURRENCY.get(country, "EUR")
    rate = VAT_RATES[country]
    issued = date(2026, 1, 5) + timedelta(days=rng.randrange(0, 264))
    days = rng.choice([14, 30, 30, 45, 60])
    due = issued + timedelta(days=days)
    amount_style, date_style, variant = rng.randrange(2), rng.randrange(4), rng.randrange(2)
    iban_style = 0 if rng.random() < 0.8 else 1
    doc_no = _doc_number(rng, lang, kind, issued)

    lines, subtotal, vat, fee, instalments = [], None, None, None, None
    if kind == "invoice":
        for _ in range(rng.randint(1, 4)):
            qty, unit = rng.randint(1, 12), Decimal(rng.randrange(2500, 240000)) / 100
            lines.append({"text": rng.choice(LINE_ITEMS[lang]), "qty": str(qty), "unit": unit, "amount": unit * qty})
        subtotal = sum((line["amount"] for line in lines), Decimal("0"))
    elif kind == "contract":
        instalments = rng.choice([3, 4, 6, 12])
        subtotal = Decimal(rng.randrange(160, 1800) * 25)
        fee = subtotal * instalments
    if subtotal is not None:
        subtotal = _money(subtotal)
        vat = _money(subtotal * rate / 100)
        total = subtotal + vat
    else:
        total = Decimal(rng.randrange(30000, 2500000)) / 100

    iban, bic, notice = vendor["iban"], vendor["bic"], ""
    trap = plan["trap"]
    if trap == "iban_checksum":
        check = int(iban[2:4])
        wrong = (check + rng.randint(1, 9)) % 100
        iban = f"{iban[:2]}{wrong:02d}{iban[4:]}"
    elif trap == "vendor_bank_change":
        bank = rng.choice([b for b in banks if b["country"] == country])
        iban, bic = make_iban(country, make_bban(country, bank["bank_code"], rng)), bank["bic"]
        if kind == "payment_request" and rng.random() < 0.5:
            notice = BANK_CHANGE_NOTICE[lang]
    elif trap == "bic_mismatch":
        bic = rng.choice([b for b in banks if b["country"] == country and b["bic"] != bic])["bic"]
    elif trap == "total_mismatch":
        total += Decimal(rng.choice([10, 45, 90, 100, 900]))
    elif trap == "due_before_issue":
        due = issued - timedelta(days=rng.randint(5, 40))

    bank_name = next(
        (b["name"] for b in banks if b["country"] == country and iban[4:].startswith(b["bank_code"])), banks[0]["name"]
    )
    bic_printed = bic[:8] if rng.random() < 0.3 else bic
    terms = TERMS[lang].format(days=days) if plan["terms"] else ""
    printed = {
        "counterparty": vendor["name"],
        "document_number": doc_no,
        "document_date": fmt_date(issued, lang, date_style),
        "due_date": terms or fmt_date(due, lang, date_style),
        "amount": fmt_amount(total, currency, lang, amount_style),
        "iban": fmt_iban(iban, iban_style),
        "bic": bic_printed,
    }
    d = {
        "vendor": vendor["name"],
        "street": vendor["street"],
        "city": vendor["city"],
        "city_line": vendor["city_line"],
        "vat_id": vendor["vat_id"],
        "doc_no": doc_no,
        "doc_date": printed["document_date"],
        "due_date": printed["due_date"] if not terms else "",
        "terms": terms,
        "po": f"PO-{_digits(rng, 5)}",
        "lines": [
            {
                "text": line["text"],
                "qty": line["qty"],
                "unit": fmt_number(line["unit"], lang),
                "amount": fmt_number(line["amount"], lang),
            }
            for line in lines
        ],
        "subtotal": fmt_amount(subtotal, currency, lang, amount_style) if subtotal is not None else "",
        "vat": fmt_amount(vat, currency, lang, amount_style) if vat is not None else "",
        "total": printed["amount"],
        "rate": rate,
        "fee": fmt_amount(fee, currency, lang, amount_style) if fee is not None else "",
        "instalments": instalments,
        "bank": bank_name,
        "iban": printed["iban"],
        "bic": bic_printed,
        "notice": notice,
        "person": rng.choice(PEOPLE[lang]),
    }
    clean_text = TEMPLATES[(lang, kind)](d, variant)
    text = scan_noise(clean_text, issued, lang, rng) if plan["scan"] else clean_text
    label = {
        "id": doc_id,
        "file": f"docs/{doc_id}.txt",
        "language": lang,
        "type": kind,
        "vendor_id": vendor.get("vendor_id"),
        "scan": plan["scan"],
        "trap": trap,
        "review_field": TRAP_FIELD.get(trap),
        "new_vendor": plan["new_vendor"],
        "must_review": trap is not None or plan["new_vendor"],
        "due_from_terms": bool(terms),
        "fields": {
            "counterparty": vendor["name"],
            "document_number": doc_no,
            "document_date": issued.isoformat(),
            "due_date": due.isoformat(),
            "amount": {"value": f"{total:.2f}", "currency": currency},
            "iban": iban,
            "bic": bic11(bic_printed),
        },
        "subtotal": f"{subtotal:.2f}" if subtotal is not None else None,
        "vat": f"{vat:.2f}" if vat is not None else None,
        "printed": printed,
    }
    return {"id": doc_id, "text": text, "clean_text": clean_text, "label": label}


def build_split(seed: int, n: int, prefix: str, reference: dict) -> list[dict]:
    rng = random.Random(seed)
    languages = (["en", "fr", "de"] * (n // 3 + 1))[:n]
    rng.shuffle(languages)
    kinds = [rng.choices(["invoice", "payment_request", "contract"], weights=[6, 2, 2])[0] for _ in range(n)]
    terms = [kind == "invoice" and rng.random() < 0.25 for kind in kinds]
    new_vendors = set(rng.sample(range(n), round(NEW_VENDOR_SHARE * n)))

    traps: dict[int, str] = {}
    for number in range(round(TRAP_SHARE * n)):
        trap = TRAP_TYPES[number % len(TRAP_TYPES)]
        eligible = [
            i
            for i in range(n)
            if i not in new_vendors
            and i not in traps
            and not (trap == "total_mismatch" and kinds[i] == "payment_request")
            and not (trap == "due_before_issue" and terms[i])
        ]
        traps[rng.choice(eligible)] = trap
    scans = set(rng.sample(range(n), round(SCAN_SHARE * n)))

    taken = list(reference["taken"])
    documents = []
    for i in range(n):
        lang = languages[i]
        if i in new_vendors:
            country = rng.choice([c for c, _ in VENDOR_COUNTRIES[lang]])
            vendor = make_vendor(rng, lang, country, reference["banks"], taken)
        else:
            vendor = rng.choice([v for v in reference["vendors"] if LANGUAGE_OF_COUNTRY[v["country"]] == lang])
        plan = {"trap": traps.get(i), "scan": i in scans, "new_vendor": i in new_vendors, "terms": terms[i]}
        documents.append(make_document(rng, f"{prefix}-{i + 1:03d}", lang, kinds[i], vendor, plan, reference))
    return documents


def _csv(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def all_files() -> dict[str, str]:
    reference = build_reference()
    files = {
        "reference/banks.csv": _csv(reference["banks"], ["country", "bank_code", "bic", "name"]),
        "reference/vendors.csv": _csv(
            reference["vendors"], ["vendor_id", "name", "country", "street", "city_line", "vat_id", "iban", "bic"]
        ),
    }
    for split, (seed, n, prefix) in SPLITS.items():
        documents = build_split(seed, n, prefix, reference)
        for document in documents:
            files[f"{split}/docs/{document['id']}.txt"] = document["text"]
        files[f"{split}/labels.jsonl"] = "".join(
            json.dumps(document["label"], ensure_ascii=False) + "\n" for document in documents
        )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    args = parser.parse_args()
    files = all_files()
    if args.check:
        stale = [path for path, content in files.items() if not (HERE / path).exists() or (HERE / path).read_text(encoding="utf-8") != content]
        for path in stale:
            print(f"differs: data/{path}")
        print("data is up to date" if not stale else f"{len(stale)} file(s) differ: run `make data`")
        return 1 if stale else 0
    for path, content in files.items():
        target = HERE / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"wrote {len(files)} files under data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
