"""Shared reversal-guard + orchestration helpers for the reversal views.

The adjustment, item-adjustment, operation and transaction reversal views all
guard against reversing a record that is already reversed or that is itself a
reversal. This module centralises the exact user-facing messages (kept
byte-for-byte identical so the existing translations in
``locale/*/LC_MESSAGES/django.po`` keep matching) and the POST/reverse/audit
scaffolding shared by every reversal view.
"""
import traceback

from django.contrib import messages
from django.utils.translation import gettext as _

from apps.app_base.logging_utils import audit_logger, logger

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


def request_reversal(
    request,
    obj,
    *,
    record_type,
    reverse_call,
    audit_success,
    audit_failure,
    success_message,
    error_message,
    redirect_to,
    missing_reason_audit=None,
    error_details_extra=None,
):
    """Process a POSTed reversal request for *obj* (shared by the reversal views).

    Reads ``reversal_reason`` from the POST data, requires it non-empty, performs
    the reversal via ``reverse_call(officer, reason)`` and writes the audit trail
    and user messages. Returns the redirect response on success, or ``None`` when
    a reason is missing or the reversal failed — the caller re-renders its form
    (the error message has already been set).

    Callbacks:
      - ``reverse_call(officer, reason)`` — performs ``obj.reverse(...)`` and
        returns the reversal record (may be None).
      - ``audit_success(request, obj, reason, reversal)`` — returns the
        ``audit_logger.info`` line.
      - ``audit_failure(request, obj, error, error_details)`` — returns the
        ``audit_logger.error`` line.
      - ``success_message(request, obj, reason)`` — returns the success text.
      - ``error_message(error)`` — returns the failure text.
      - ``redirect_to(obj)`` — returns the success redirect response.
      - ``missing_reason_audit(request, obj)`` — optional; when provided the
        missing-reason branch also writes this ``audit_logger.info`` line.
      - ``error_details_extra(obj)`` — optional extra keys merged into the
        failure ``error_details`` dict.
    """
    reason = request.POST.get("reversal_reason", "").strip()
    if not reason:
        error_msg = _("A reason for reversal is required.")
        logger.warning(f"{error_msg} | record={obj.pk}")
        if missing_reason_audit is not None:
            audit_logger.info(missing_reason_audit(request, obj))
        messages.error(request, error_msg)
        return None

    officer = request.user
    try:
        logger.debug(f"Executing {record_type} reversal")
        reversal = reverse_call(officer, reason)
        audit_logger.info(audit_success(request, obj, reason, reversal))
        messages.success(request, success_message(request, obj, reason))
        return redirect_to(obj)
    except Exception as e:
        traceback.print_exc()
        error_details = {
            "exception_type": type(e).__name__,
            "error_message": str(e),
            "officer": officer.username,
            "traceback": traceback.format_exc(),
        }
        if error_details_extra is not None:
            error_details.update(error_details_extra(obj))
        audit_logger.error(audit_failure(request, obj, e, error_details))
        messages.error(request, error_message(e))
        return None
