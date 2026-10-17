"""Tests for the ``purge_savelogs`` management command."""

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.app_audit.models import ActionTrace, SaveLog


class PurgeSaveLogsTests(TestCase):
    def setUp(self):
        self.trace = ActionTrace.objects.create(method="POST", path="/x/")
        self.old = SaveLog.objects.create(
            trace=self.trace,
            app_label="app_operation",
            model="operation",
            object_id="1",
            kind="create",
        )
        self.new = SaveLog.objects.create(
            trace=self.trace,
            app_label="app_operation",
            model="operation",
            object_id="2",
            kind="create",
            is_derived=True,
        )
        # auto_now_add: force an old timestamp for the cutoff tests.
        SaveLog.objects.filter(pk=self.old.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )

    def test_dry_run_keeps_rows(self):
        call_command("purge_savelogs", "--older-than", "90", "--dry-run", stdout=_Null())
        self.assertEqual(SaveLog.objects.count(), 2)

    def test_older_than_deletes_only_old(self):
        call_command(
            "purge_savelogs",
            "--older-than",
            "90",
            "--keep-traces",
            stdout=_Null(),
        )
        self.assertEqual(list(SaveLog.objects.values_list("pk", flat=True)), [self.new.pk])

    def test_level_derived_only(self):
        call_command("purge_savelogs", "--level", "derived-only", stdout=_Null())
        self.assertFalse(SaveLog.objects.filter(pk=self.new.pk).exists())
        self.assertTrue(SaveLog.objects.filter(pk=self.old.pk).exists())

    def test_trace_filter(self):
        other = ActionTrace.objects.create(method="POST", path="/y/")
        SaveLog.objects.create(
            trace=other, app_label="app_entity", model="entity", object_id="9", kind="create"
        )
        call_command("purge_savelogs", "--trace", str(self.trace.pk), stdout=_Null())
        self.assertEqual(SaveLog.objects.count(), 1)
        self.assertEqual(SaveLog.objects.get().trace_id, other.pk)

    def test_model_filter(self):
        SaveLog.objects.create(
            app_label="app_entity", model="entity", object_id="9", kind="create"
        )
        call_command(
            "purge_savelogs", "--model", "app_entity.Entity", stdout=_Null()
        )
        self.assertEqual(SaveLog.objects.filter(app_label="app_entity").count(), 0)

    def test_orphan_traces_purged_by_default(self):
        call_command("purge_savelogs", stdout=_Null())
        self.assertFalse(ActionTrace.objects.exists())

    def test_keep_traces_flag(self):
        call_command("purge_savelogs", "--keep-traces", stdout=_Null())
        self.assertTrue(ActionTrace.objects.exists())


class _Null:
    """Swallow command output."""

    def write(self, *_args, **_kwargs):
        pass

    def flush(self):
        pass
