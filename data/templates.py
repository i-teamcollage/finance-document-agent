"""Document layouts in English, French and German: invoices, payment requests and contract extracts.

Each template receives `d`, a dict of strings exactly as they will be printed, and returns plain text.
Two layouts per language and type, with the label synonyms real back offices see.
"""

from __future__ import annotations

from decimal import Decimal

from words import CLIENT, MONTH_NAMES


def fmt_number(value: Decimal, lang: str) -> str:
    whole, cents = f"{value:.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    if lang == "en":
        return ",".join(groups) + "." + cents
    if lang == "fr":
        return "\u202f".join(groups) + "," + cents
    return ".".join(groups) + "," + cents


def fmt_amount(value: Decimal, currency: str, lang: str, style: int) -> str:
    symbol = {"EUR": "€", "GBP": "£"}[currency]
    if lang == "en":
        number = fmt_number(value, "en")
        return f"{symbol}{number}" if style == 0 else f"{currency} {number}"
    if lang == "fr":
        number = fmt_number(value, "fr")
        if style == 1:
            number = number.replace("\u202f", " ")
            return f"{number} {currency}"
        return f"{number} {symbol}"
    number = fmt_number(value, "de")
    return f"{number} {symbol}" if style == 0 else f"{currency} {number}"


def fmt_date(value, lang: str, style: int) -> str:
    if lang == "en":
        return [
            value.strftime("%d/%m/%Y"),
            f"{value.day} {MONTH_NAMES['en'][value.month - 1]} {value.year}",
            value.isoformat(),
            f"{value.day:02d} {MONTH_NAMES['en'][value.month - 1][:3]} {value.year}",
        ][style % 4]
    if lang == "fr":
        if style % 2 == 0:
            return value.strftime("%d/%m/%Y")
        day = "1er" if value.day == 1 else str(value.day)
        return f"{day} {MONTH_NAMES['fr'][value.month - 1]} {value.year}"
    if style % 2 == 0:
        return value.strftime("%d.%m.%Y")
    return f"{value.day}. {MONTH_NAMES['de'][value.month - 1]} {value.year}"


def fmt_iban(iban: str, style: int) -> str:
    if style == 1:
        return iban
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _lines_table(d: dict, headers: tuple[str, str, str, str]) -> str:
    rows = [f"{headers[0]:<38}{headers[1]:>6}{headers[2]:>16}{headers[3]:>16}"]
    for line in d["lines"]:
        rows.append(f"{line['text']:<38}{line['qty']:>6}{line['unit']:>16}{line['amount']:>16}")
    return "\n".join(rows)


def _totals(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{'':<38}{label:<22}{value:>16}" for label, value in pairs)


# ---------------------------------------------------------------- English


def en_invoice(d: dict, variant: int) -> str:
    due = f"Payment terms:  {d['terms']}" if d["terms"] else f"Due Date:       {d['due_date']}"
    if variant == 0:
        return f"""{d["vendor"]}
{d["street"]}
{d["city_line"]}
VAT No: {d["vat_id"]}

INVOICE

Invoice No:     {d["doc_no"]}
Invoice Date:   {d["doc_date"]}
{due}
Customer:       {CLIENT["name"]}
                {CLIENT["street"]}, {CLIENT["city_line"]}
Customer ref:   {d["po"]}

{_lines_table(d, ("Description", "Qty", "Unit price", "Amount"))}

{_totals([("Subtotal", d["subtotal"]), (f"VAT {d['rate']}%", d["vat"]), ("Total due", d["total"])])}

Please pay to:
Bank:       {d["bank"]}
IBAN:       {d["iban"]}
BIC:        {d["bic"]}
Reference:  {d["doc_no"]}
"""
    due = f"Terms: {d['terms']}" if d["terms"] else f"Payment due: {d['due_date']}"
    return f"""TAX INVOICE                                   {d["vendor"]}
                                              {d["street"]}, {d["city_line"]}

Bill to:
{CLIENT["name"]}
{CLIENT["street"]}
{CLIENT["city_line"]}

Invoice number: {d["doc_no"]}        Date of issue: {d["doc_date"]}
{due}        Your order: {d["po"]}

{_lines_table(d, ("Item", "Qty", "Rate", "Line total"))}

{_totals([("Net amount", d["subtotal"]), (f"VAT at {d['rate']}%", d["vat"]), ("Amount payable", d["total"])])}

Remittance details
Account name: {d["vendor"]}
IBAN: {d["iban"]}    SWIFT/BIC: {d["bic"]}
{d["bank"]}
Company VAT registration {d["vat_id"]}
"""


def en_payment_request(d: dict, variant: int) -> str:
    opener = "Dear Sir or Madam," if variant == 0 else f"Dear {CLIENT['name']} accounts team,"
    return f"""{d["vendor"]}
{d["street"]}, {d["city_line"]}

{CLIENT["name"]}
Accounts Payable
{CLIENT["street"]}
{CLIENT["city_line"]}

{d["city"]}, {d["doc_date"]}

Our reference: {d["doc_no"]}

PAYMENT REQUEST

{opener}

Please arrange payment of {d["total"]} for the services delivered under your purchase order
{d["po"]}. The amount is due by {d["due_date"]}.

Payment details
Beneficiary: {d["vendor"]}
IBAN: {d["iban"]}
BIC/SWIFT: {d["bic"]}
Bank: {d["bank"]}
{d["notice"]}
Kind regards,

{d["person"]}
Finance Department
"""


def en_contract(d: dict, variant: int) -> str:
    heading = (
        "SERVICE AGREEMENT - PAYMENT SCHEDULE (EXTRACT)" if variant == 0 else "MASTER SERVICES AGREEMENT (EXTRACT)"
    )
    return f"""{heading}

Agreement No. {d["doc_no"]}
Between {CLIENT["name"]}, {CLIENT["street"]}, {CLIENT["city_line"]} ("the Client")
and {d["vendor"]}, {d["street"]}, {d["city_line"]} ("the Supplier").
Date of agreement: {d["doc_date"]}

4. Fees and payment
4.1 The Client shall pay the Supplier a fee of {d["fee"]} excluding VAT, in {d["instalments"]} instalments.
4.2 The first instalment of {d["subtotal"]} plus VAT at {d["rate"]}% ({d["vat"]}), together {d["total"]},
    is due on {d["due_date"]}.
4.3 Payments shall be made to the Supplier's account IBAN {d["iban"]}, BIC {d["bic"]},
    held with {d["bank"]}.
4.4 Late payments bear interest at the statutory rate.

Signed for the Supplier: {d["person"]}
"""


# ---------------------------------------------------------------- French


def fr_invoice(d: dict, variant: int) -> str:
    due = f"Conditions de paiement : {d['terms']}" if d["terms"] else f"Date d'échéance : {d['due_date']}"
    if variant == 0:
        totals = _totals(
            [
                ("Total HT", d["subtotal"]),
                (f"TVA {d['rate']} %", d["vat"]),
                ("Total TTC", d["total"]),
                ("Net à payer", d["total"]),
            ]
        )
        return f"""{d["vendor"]}
{d["street"]}
{d["city_line"]}
N° TVA intracommunautaire : {d["vat_id"]}

FACTURE N° {d["doc_no"]}

Date de facture : {d["doc_date"]}
{due}
Client : {CLIENT["name"]}, {CLIENT["street"]}, {CLIENT["city_line"]}
Votre commande : {d["po"]}

{_lines_table(d, ("Désignation", "Qté", "P.U. HT", "Montant HT"))}

{totals}

Règlement par virement
Banque : {d["bank"]}
IBAN : {d["iban"]}
BIC : {d["bic"]}
"""
    due = f"Paiement : {d['terms']}" if d["terms"] else f"Échéance : {d['due_date']}"
    return f"""{d["vendor"]} - {d["street"]} - {d["city_line"]}

                                    {CLIENT["name"]}
                                    {CLIENT["street"]}
                                    {CLIENT["city_line"]}

Facture n° {d["doc_no"]}
Date d'émission : {d["doc_date"]}
{due}
Réf. commande : {d["po"]}

{_lines_table(d, ("Prestation", "Qté", "Prix unitaire", "Total HT"))}

{_totals([("Montant HT", d["subtotal"]), (f"TVA ({d['rate']} %)", d["vat"]), ("Montant TTC", d["total"])])}

Coordonnées bancaires : {d["bank"]}
IBAN {d["iban"]} - Code BIC {d["bic"]}
TVA intracom. {d["vat_id"]}
"""


def fr_payment_request(d: dict, variant: int) -> str:
    objet = "demande de règlement" if variant == 0 else "appel de paiement"
    return f"""{d["vendor"]}
{d["street"]}
{d["city_line"]}

À l'attention du service comptabilité fournisseurs
{CLIENT["name"]}
{CLIENT["street"]}
{CLIENT["city_line"]}

{d["city"]}, le {d["doc_date"]}

Objet : {objet} - notre réf. {d["doc_no"]}

Madame, Monsieur,

Nous vous prions de bien vouloir procéder au règlement de la somme de {d["total"]},
correspondant aux prestations réalisées dans le cadre de votre commande {d["po"]},
au plus tard le {d["due_date"]}.

Bénéficiaire : {d["vendor"]}
IBAN : {d["iban"]}
BIC : {d["bic"]}
Banque : {d["bank"]}
{d["notice"]}
Nous vous prions d'agréer, Madame, Monsieur, nos salutations distinguées.

{d["person"]}
Service financier
"""


def fr_contract(d: dict, variant: int) -> str:
    heading = "CONTRAT DE PRESTATION DE SERVICES - EXTRAIT" if variant == 0 else "CONTRAT-CADRE DE SERVICES (EXTRAIT)"
    return f"""{heading}

Contrat n° {d["doc_no"]}
Entre {CLIENT["name"]}, {CLIENT["street"]}, {CLIENT["city_line"]} (« le Client »)
et {d["vendor"]}, {d["street"]}, {d["city_line"]} (« le Prestataire »).
Fait à {d["city"]}, le {d["doc_date"]}

Article 5 - Rémunération et modalités de paiement
5.1 Le Client verse au Prestataire une rémunération de {d["fee"]} HT, payable en {d["instalments"]} échéances.
5.2 La première échéance, d'un montant de {d["subtotal"]} HT, majoré de la TVA à {d["rate"]} % ({d["vat"]}),
    soit {d["total"]} TTC, est exigible le {d["due_date"]}.
5.3 Les paiements sont effectués par virement sur le compte du Prestataire :
    IBAN {d["iban"]} - BIC {d["bic"]} ({d["bank"]}).

Pour le Prestataire : {d["person"]}
"""


# ---------------------------------------------------------------- German


def de_invoice(d: dict, variant: int) -> str:
    due = d["terms"] if d["terms"] else f"Fällig am: {d['due_date']}"
    if variant == 0:
        return f"""{d["vendor"]} · {d["street"]} · {d["city_line"]}

{CLIENT["name"]}
{CLIENT["street"]}
L-1611 Luxemburg

RECHNUNG

Rechnungsnummer: {d["doc_no"]}
Rechnungsdatum:  {d["doc_date"]}
{due}
Ihre Bestellung: {d["po"]}
USt-IdNr.:       {d["vat_id"]}

{_lines_table(d, ("Bezeichnung", "Menge", "Einzelpreis", "Gesamt"))}

{_totals([("Nettobetrag", d["subtotal"]), (f"zzgl. {d['rate']} % USt", d["vat"]), ("Rechnungsbetrag", d["total"])])}

Bankverbindung: {d["bank"]}
IBAN: {d["iban"]}
BIC: {d["bic"]}
Bitte geben Sie bei Zahlung die Rechnungsnummer an.
"""
    due = f"Zahlungsziel: {d['terms']}" if d["terms"] else f"Zahlbar bis: {d['due_date']}"
    return f"""                                            {d["vendor"]}
                                            {d["street"]}
                                            {d["city_line"]}

An: {CLIENT["name"]}, {CLIENT["street"]}, L-1611 Luxemburg

Rechnung Nr. {d["doc_no"]}
Datum: {d["doc_date"]}
{due}
Bestellnummer: {d["po"]}

{_lines_table(d, ("Leistung", "Menge", "Preis", "Betrag"))}

{_totals([("Summe netto", d["subtotal"]), (f"MwSt. {d['rate']} %", d["vat"]), ("Gesamtbetrag", d["total"])])}

Empfänger: {d["vendor"]}
Kreditinstitut: {d["bank"]}
IBAN {d["iban"]}  ·  BIC {d["bic"]}
"""


def de_payment_request(d: dict, variant: int) -> str:
    subject = "Zahlungsaufforderung" if variant == 0 else "Bitte um Zahlung"
    return f"""{d["vendor"]}
{d["street"]}
{d["city_line"]}

{CLIENT["name"]}
Kreditorenbuchhaltung
{CLIENT["street"]}
L-1611 Luxemburg

{d["city"]}, den {d["doc_date"]}

{subject} - Ihr Zeichen {d["po"]}, unser Zeichen {d["doc_no"]}

Sehr geehrte Damen und Herren,

wir bitten Sie, den Betrag von {d["total"]} bis spätestens {d["due_date"]} auf das unten
genannte Konto zu überweisen.

Empfänger: {d["vendor"]}
IBAN: {d["iban"]}
BIC: {d["bic"]}
Bank: {d["bank"]}
{d["notice"]}
Mit freundlichen Grüßen

{d["person"]}
Finanzbuchhaltung
"""


def de_contract(d: dict, variant: int) -> str:
    heading = "DIENSTLEISTUNGSVERTRAG - AUSZUG" if variant == 0 else "RAHMENVERTRAG ÜBER DIENSTLEISTUNGEN (AUSZUG)"
    return f"""{heading}

Vertrag Nr. {d["doc_no"]}
zwischen {CLIENT["name"]}, {CLIENT["street"]}, L-1611 Luxemburg („Auftraggeber")
und {d["vendor"]}, {d["street"]}, {d["city_line"]} („Auftragnehmer")
{d["city"]}, den {d["doc_date"]}

§ 6 Vergütung und Zahlung
(1) Der Auftraggeber zahlt dem Auftragnehmer eine Vergütung von {d["fee"]} netto, zahlbar in {d["instalments"]} Raten.
(2) Die erste Rate über {d["subtotal"]} zzgl. {d["rate"]} % USt ({d["vat"]}), insgesamt {d["total"]},
    ist am {d["due_date"]} fällig.
(3) Zahlungen erfolgen auf das Konto des Auftragnehmers: IBAN {d["iban"]}, BIC {d["bic"]}, {d["bank"]}.

Für den Auftragnehmer: {d["person"]}
"""


TEMPLATES = {
    ("en", "invoice"): en_invoice,
    ("en", "payment_request"): en_payment_request,
    ("en", "contract"): en_contract,
    ("fr", "invoice"): fr_invoice,
    ("fr", "payment_request"): fr_payment_request,
    ("fr", "contract"): fr_contract,
    ("de", "invoice"): de_invoice,
    ("de", "payment_request"): de_payment_request,
    ("de", "contract"): de_contract,
}

TERMS = {
    "en": "{days} days net",
    "fr": "à {days} jours",
    "de": "Zahlbar innerhalb von {days} Tagen netto",
}

BANK_CHANGE_NOTICE = {
    "en": "Please note: our bank details have changed. Kindly update your records.\n",
    "fr": "Merci de noter que nos coordonnées bancaires ont changé.\n",
    "de": "Bitte beachten Sie unsere geänderte Bankverbindung.\n",
}
