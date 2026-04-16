import django.db.models.deletion
from django.db import migrations, models


def copy_profit_loss_amounts(apps, schema_editor):
    ProfitLoss = apps.get_model("app_operation", "ProfitLoss")
    FinancialPeriod = apps.get_model("app_operation", "FinancialPeriod")
    for pl in ProfitLoss.all_objects.all():
        FinancialPeriod.all_objects.filter(pk=pl.period_id).update(amount=pl.amount)


def update_operation_plans(apps, schema_editor):
    ProfitLoss = apps.get_model("app_operation", "ProfitLoss")
    Operation = apps.get_model("app_operation", "Operation")
    for op in Operation.objects.filter(plan_id__isnull=False):
        pl = ProfitLoss.all_objects.get(pk=op.plan_id)
        op.plan_fp_id = pl.period_id
        op.save(update_fields=["plan_fp_id"])


def update_allocation_periods(apps, schema_editor):
    ProfitLoss = apps.get_model("app_operation", "ProfitLoss")
    ShareholderAllocation = apps.get_model("app_operation", "ShareholderAllocation")
    for alloc in ShareholderAllocation.all_objects.all():
        pl = ProfitLoss.all_objects.get(pk=alloc.plan_id)
        alloc.period_fp_id = pl.period_id
        alloc.save(update_fields=["period_fp_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("app_operation", "0006_profitloss_and_more"),
    ]

    operations = [
        # 1. Add amount to FinancialPeriod
        migrations.AddField(
            model_name="financialperiod",
            name="amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=20, null=True
            ),
        ),
        # 2. Copy ProfitLoss.amount → FinancialPeriod.amount
        migrations.RunPython(
            copy_profit_loss_amounts, reverse_code=migrations.RunPython.noop
        ),
        # 3. Add temporary FK on Operation pointing to FinancialPeriod
        migrations.AddField(
            model_name="operation",
            name="plan_fp",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plan_operations_tmp",
                to="app_operation.financialperiod",
            ),
        ),
        # 4. Populate plan_fp from Operation.plan.period
        migrations.RunPython(
            update_operation_plans, reverse_code=migrations.RunPython.noop
        ),
        # 5. Remove old Operation.plan (→ ProfitLoss)
        migrations.RemoveField(model_name="operation", name="plan"),
        # 6. Rename plan_fp → plan
        migrations.RenameField(
            model_name="operation", old_name="plan_fp", new_name="plan"
        ),
        # 7. Fix related_name on the renamed field
        migrations.AlterField(
            model_name="operation",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plan_operations",
                to="app_operation.financialperiod",
            ),
        ),
        # 8. Add temporary FK on ShareholderAllocation pointing to FinancialPeriod
        migrations.AddField(
            model_name="shareholderallocation",
            name="period_fp",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="allocations_tmp",
                to="app_operation.financialperiod",
            ),
        ),
        # 9. Populate period_fp from ShareholderAllocation.plan.period
        migrations.RunPython(
            update_allocation_periods, reverse_code=migrations.RunPython.noop
        ),
        # 10. Remove old ShareholderAllocation.plan (→ ProfitLoss)
        migrations.RemoveConstraint(
            model_name="shareholderallocation",
            name="unique_allocation_per_plan_shareholder",
        ),
        migrations.RemoveField(model_name="shareholderallocation", name="plan"),
        # 11. Rename period_fp → period
        migrations.RenameField(
            model_name="shareholderallocation",
            old_name="period_fp",
            new_name="period",
        ),
        # 12. Fix related_name and nullability on the renamed field
        migrations.AlterField(
            model_name="shareholderallocation",
            name="period",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="allocations",
                to="app_operation.financialperiod",
            ),
        ),
        # 13. Add new unique constraint
        migrations.AddConstraint(
            model_name="shareholderallocation",
            constraint=models.UniqueConstraint(
                fields=("period", "shareholder"),
                name="unique_allocation_per_period_shareholder",
            ),
        ),
        # 14. Delete ProfitLoss
        migrations.RemoveConstraint(
            model_name="profitloss",
            name="unique_profit_loss_per_entity_period",
        ),
        migrations.DeleteModel(name="ProfitLoss"),
    ]
