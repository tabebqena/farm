"""Audit / provenance models powering the "What happened & why" views.

Two records work together:

- :class:`ActionTrace` — one row per mutating user action. It stores the raw
  request input (the ``payload``) so a user can see exactly what they submitted
  (display level 1: *USERINPUT*).
- :class:`SaveLog` — one row per :meth:`BaseModel.save`. It stores the row's
  full post-save shape. Every row is display level 3 (*Every save*); rows whose
  ``is_derived`` flag is set are display level 2 (*Auto-created rows*), carrying
  the ``role`` / ``reason`` that explains why the app created them.

These are infrastructure models, so they deliberately subclass
``django.db.models.Model`` rather than :class:`apps.app_base.models.BaseModel`:
they are append-only, must never be soft-deleted, and must not be tracked by
themselves. They are physically removed with ``manage.py purge_savelogs``.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SaveKind(models.TextChoices):
    """How a tracked row was written."""

    CREATE = "create", _("Create")
    UPDATE = "update", _("Update")
    SOFT_DELETE = "soft_delete", _("Soft delete")


class TraceStatus(models.TextChoices):
    """Outcome of a traced user action."""

    IN_PROGRESS = "in_progress", _("In progress")
    SUCCESS = "success", _("Success")
    FAILED = "failed", _("Failed")


class ActionTrace(models.Model):
    """One mutating user action (a request) and the input that triggered it.

    Display level 1 (*USERINPUT*). The row is created when a mutating request
    starts (and committed independently) so a failed action is still recorded
    even when the surrounding ``transaction.atomic()`` block rolls back.
    """

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("actor"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_traces",
    )
    method = models.CharField(_("method"), max_length=10, blank=True, default="")
    path = models.CharField(_("path"), max_length=512, blank=True, default="")
    action = models.CharField(_("action"), max_length=200, blank=True, default="")
    payload = models.JSONField(_("payload"), default=dict, blank=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=TraceStatus.choices,
        default=TraceStatus.IN_PROGRESS,
        db_index=True,
    )
    error = models.TextField(_("error"), blank=True, default="")
    root_app = models.CharField(_("root app"), max_length=100, blank=True, default="")
    root_model = models.CharField(_("root model"), max_length=100, blank=True, default="")
    root_pk = models.CharField(_("root pk"), max_length=64, blank=True, default="")
    group_key = models.CharField(
        _("group key"), max_length=128, blank=True, default="", db_index=True
    )
    duration_ms = models.PositiveIntegerField(_("duration (ms)"), null=True, blank=True)
    ip = models.GenericIPAddressField(_("ip"), null=True, blank=True)

    class Meta:
        verbose_name = _("action trace")
        verbose_name_plural = _("action traces")
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("actor", "created_at")),
        ]

    def __str__(self):
        who = self.actor.username if self.actor else _("anonymous")
        return f"{self.action or self.path} by {who} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    @property
    def derived_saves(self):
        """The auto-created rows recorded for this action (display level 2)."""
        return self.saves.filter(is_derived=True)

    @property
    def all_saves(self):
        """Every tracked save for this action (display level 3)."""
        return self.saves.all()


class SaveLog(models.Model):
    """One ``save()`` of a tracked model, storing the row's new shape.

    ``new_shape`` holds the row's full field values *after* the save, so it is
    self-contained and survives a later soft delete of the row. Derived rows
    (``is_derived=True``) also carry ``role`` / ``reason_code`` / ``reason_text``
    describing which app rule created them and why.
    """

    trace = models.ForeignKey(
        ActionTrace,
        verbose_name=_("action trace"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="saves",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("actor"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="save_logs",
    )
    app_label = models.CharField(_("app label"), max_length=100)
    model = models.CharField(_("model"), max_length=100)
    object_id = models.CharField(_("object id"), max_length=64)
    object_repr = models.CharField(_("object"), max_length=255, blank=True, default="")
    kind = models.CharField(_("kind"), max_length=20, choices=SaveKind.choices)
    new_shape = models.JSONField(_("new shape"), default=dict, blank=True)
    is_derived = models.BooleanField(_("auto-created"), default=False, db_index=True)
    role = models.CharField(_("role"), max_length=100, blank=True, default="")
    reason_code = models.CharField(
        _("reason code"), max_length=100, blank=True, default=""
    )
    reason_text = models.TextField(_("reason"), blank=True, default="")
    origin = models.CharField(_("origin"), max_length=32, blank=True, default="")

    class Meta:
        verbose_name = _("save log")
        verbose_name_plural = _("save logs")
        ordering = ("pk",)
        indexes = [
            models.Index(fields=("app_label", "model", "object_id")),
            models.Index(fields=("trace", "created_at")),
            models.Index(fields=("is_derived", "created_at")),
        ]

    def __str__(self):
        tag = f" [{self.role}]" if self.is_derived else ""
        return f"{self.app_label}.{self.model}:{self.object_id} ({self.kind}){tag}"
