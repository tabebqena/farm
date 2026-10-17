"""Human explanations for the auto-creation rules recorded in ``SaveLog``.

Each derived save carries a ``reason_code``; this catalog maps those codes to a
plain-language explanation of *why* the app created the row. The text is stored
denormalised on the row at write time (so the UI never depends on this module
outliving the code path that produced it), but this remains the single source
of truth and is cross-referenced by the operation specs under ``docs/``.
"""

# Auto-creation roles (what a derived row *is*).
ROLE_ISSUANCE_TXN = "ISSUANCE_TXN"
ROLE_PAYMENT_TXN = "PAYMENT_TXN"
ROLE_REPAYMENT_TXN = "REPAYMENT_TXN"
ROLE_BIRTH_LINE = "BIRTH_LINE"
ROLE_DEATH_LINE = "DEATH_LINE"
ROLE_CONSUMPTION_LINE = "CONSUMPTION_LINE"
ROLE_PRODUCT = "PRODUCT"
ROLE_MOVEMENT_LINE = "MOVEMENT_LINE"
ROLE_PERIOD = "PERIOD"
ROLE_VALUATION = "CAPITAL_VALUATION"
ROLE_REVERSAL = "REVERSAL"

# Reason codes (why the row was created).
REASON_AUTO_ISSUANCE = "AUTO_ISSUANCE"
REASON_AUTO_PAYMENT = "AUTO_PAYMENT"
REASON_AUTO_REPAYMENT = "AUTO_REPAYMENT"
REASON_AUTO_BIRTH_LINE = "AUTO_BIRTH_LINE"
REASON_AUTO_DEATH_LINE = "AUTO_DEATH_LINE"
REASON_AUTO_CONSUMPTION_LINE = "AUTO_CONSUMPTION_LINE"
REASON_AUTO_PRODUCT = "AUTO_PRODUCT"
REASON_AUTO_MOVEMENT = "AUTO_MOVEMENT"
REASON_PERIOD_ASSIGNED = "PERIOD_ASSIGNED"
REASON_PERIOD_CREATED = "PERIOD_CREATED"
REASON_PERIOD_CLOSED = "PERIOD_CLOSED"
REASON_CAPITAL_VALUATION = "CAPITAL_VALUATION"
REASON_REVERSAL = "REVERSAL"

REASONS = {
    REASON_AUTO_ISSUANCE: (
        "An obligation (issuance) transaction is created automatically when this "
        "record is first saved, to reflect the amount owed between its funds."
    ),
    REASON_AUTO_PAYMENT: (
        "A payment transaction is created automatically to settle this record's "
        "obligation from its configured payment source."
    ),
    REASON_AUTO_REPAYMENT: (
        "A repayment transaction is created automatically to return funds to the "
        "party that financed this record."
    ),
    REASON_AUTO_BIRTH_LINE: (
        "A stock-in movement line is generated automatically because this "
        "operation records animals born into the herd."
    ),
    REASON_AUTO_DEATH_LINE: (
        "A stock-out movement line is generated automatically because this "
        "operation records animals removed from the herd."
    ),
    REASON_AUTO_CONSUMPTION_LINE: (
        "A stock-out movement line is generated automatically to consume the "
        "inventory tied to this operation."
    ),
    REASON_AUTO_PRODUCT: (
        "A product row is created lazily on first reference, because the movement "
        "or invoice line targets a product that did not exist yet."
    ),
    REASON_AUTO_MOVEMENT: (
        "An inventory movement line is created automatically as a side effect of "
        "this operation."
    ),
    REASON_PERIOD_ASSIGNED: (
        "The operation was associated with the financial period covering its date "
        "so it is reflected in the right set of statements."
    ),
    REASON_PERIOD_CREATED: (
        "A financial period was opened automatically to cover the date of this "
        "record because no period existed for it."
    ),
    REASON_PERIOD_CLOSED: (
        "The financial period was closed automatically as part of this action."
    ),
    REASON_CAPITAL_VALUATION: (
        "A capital valuation was added automatically to revalue the affected "
        "product/inventory."
    ),
    REASON_REVERSAL: (
        "A counter-record was created automatically to reverse an earlier entry, "
        "preserving the audit trail instead of editing it."
    ),
}


def reason_text(code: str) -> str:
    """Return the human explanation for *code* (empty string when unknown)."""
    if not code:
        return ""
    return REASONS.get(code, "")
