"""Shared reversal-guard helpers for the reversal views.

The adjustment, item-adjustment, operation and transaction reversal views all
guard against reversing a record that is already reversed or that is itself a
reversal. This module centralises the exact user-facing messages (kept
byte-for-byte identical so the existing translations in
``locale/*/LC_MESSAGES/django.po`` keep matching).
"""
from django.utils.translation import gettext as _

_ALREADY_REVERSED = {
    "adjustment": _("This adjustment has already been reversed."),
    "item_adjustment": _("This item adjustment has already been reversed."),
    "operation": _("This operation has already been reversed."),
    "transaction": _("This transaction has already been reversed."),
}

_IS_REVERSAL = {
    "adjustment": _("This adjustment is a reversal (you can't reverse it)."),
    "item_adjustment": _(
        "This item adjustment is a reversal (you can't reverse it)."
    ),
    "operation": _("This operation is a reversal (You can't reverse it)."),
    "transaction": _("This transaction is a reversal (You can't reverse it)."),
}


def reversal_guard_error(obj, record_type):
    """
    Return the translated message blocking *obj* from being reversed, or None.

    Covers the shared ``is_reversed`` / ``is_reversal`` flags used by
    ``Adjustment``, ``InvoiceItemAdjustment``, ``Operation`` and ``Transaction``.
    *record_type* is one of "adjustment", "item_adjustment", "operation",
    "transaction".
    """
    if getattr(obj, "is_reversed", False):
        return _ALREADY_REVERSED[record_type]
    if getattr(obj, "is_reversal", False):
        return _IS_REVERSAL[record_type]
    return None
