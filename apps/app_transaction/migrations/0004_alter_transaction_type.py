from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_transaction", "0003_alter_transaction_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="type",
            field=models.CharField(
                choices=[
                    ("PURCHASE_ISSUANCE", "PURCHASE_ISSUANCE"),
                    ("PURCHASE_PAYMENT", "PURCHASE_PAYMENT"),
                    ("PURCHASE_ADJUSTMENT_INCREASE", "PURCHASE_ADJUSTMENT_INCREASE"),
                    ("PURCHASE_ADJUSTMENT_DECREASE", "PURCHASE_ADJUSTMENT_DECREASE"),
                    ("SALE_ISSUANCE", "SALE_ISSUANCE"),
                    ("SALE_COLLECTION", "SALE_COLLECTION"),
                    ("SALE_ADJUSTMENT_INCREASE", "SALE_ADJUSTMENT_INCREASE"),
                    ("SALE_ADJUSTMENT_DECREASE", "SALE_ADJUSTMENT_DECREASE"),
                    ("EXPENSE_ISSUANCE", "EXPENSE_ISSUANCE"),
                    ("EXPENSE_PAYMENT", "EXPENSE_PAYMENT"),
                    ("EXPENSE_ADJUSTMENT_INCREASE", "EXPENSE_ADJUSTMENT_INCREASE"),
                    ("EXPENSE_ADJUSTMENT_DECREASE", "EXPENSE_ADJUSTMENT_DECREASE"),
                    ("WORKER_ADVANCE_ISSUANCE", "WORKER_ADVANCE_ISSUANCE"),
                    ("WORKER_ADVANCE_PAYMENT", "WORKER_ADVANCE_PAYMENT"),
                    (
                        "WORKER_ADVANCE_REPAYMENT_PAYEMENT",
                        "WORKER_ADVANCE_REPAYMENT_PAYEMENT",
                    ),
                    ("CASH_INJECTION_ISSUANCE", "CASH_INJECTION_ISSUANCE"),
                    ("CASH_INJECTION_PAYMENT", "CASH_INJECTION_PAYMENT"),
                    ("CAPITAL_WITHDRAWAL_ISSUANCE", "CAPITAL_WITHDRAWAL_ISSUANCE"),
                    ("CAPITAL_WITHDRAWAL_PAYMENT", "CAPITAL_WITHDRAWAL_PAYMENT"),
                    ("CAPITAL_GAIN_ISSUANCE", "CAPITAL_GAIN_ISSUANCE"),
                    ("CAPITAL_GAIN_PAYMENT", "CAPITAL_GAIN_PAYMENT"),
                    ("CAPITAL_LOSS_ISSUANCE", "CAPITAL_LOSS_ISSUANCE"),
                    ("CAPITAL_LOSS_PAYMENT", "CAPITAL_LOSS_PAYMENT"),
                    ("LOSS_COVERAGE_ISSUANCE", "LOSS_COVERAGE_ISSUANCE"),
                    ("LOSS_COVERAGE_PAYMENT", "LOSS_COVERAGE_PAYMENT"),
                    ("PROFIT_DISTRIBUTION_ISSUANCE", "PROFIT_DISTRIBUTION_ISSUANCE"),
                    ("PROFIT_DISTRIBUTION_PAYMENT", "PROFIT_DISTRIBUTION_PAYMENT"),
                    ("PROJECT_FUNDING_ISSUANCE", "PROJECT_FUNDING_ISSUANCE"),
                    ("PROJECT_FUNDING_PAYMENT", "PROJECT_FUNDING_PAYMENT"),
                    ("PROJECT_REFUND_ISSUANCE", "PROJECT_REFUND_ISSUANCE"),
                    ("PROJECT_REFUND_PAYMENT", "PROJECT_REFUND_PAYMENT"),
                    ("LOAN_ISSUANCE", "LOAN_ISSUANCE"),
                    ("LOAN_PAYMENT", "LOAN_PAYMENT"),
                    ("LOAN_REPAYMENT", "LOAN_REPAYMENT"),
                    ("CORRECTION_CREDIT_ISSUANCE", "CORRECTION_CREDIT_ISSUANCE"),
                    ("CORRECTION_CREDIT_PAYMENT", "CORRECTION_CREDIT_PAYMENT"),
                    ("CORRECTION_DEBIT_ISSUANCE", "CORRECTION_DEBIT_ISSUANCE"),
                    ("CORRECTION_DEBIT_PAYMENT", "CORRECTION_DEBIT_PAYMENT"),
                    ("INTERNAL_TRANSFER_ISSUANCE", "INTERNAL_TRANSFER_ISSUANCE"),
                    ("INTERNAL_TRANSFER_PAYMENT", "INTERNAL_TRANSFER_PAYMENT"),
                ],
                max_length=50,
            ),
        ),
    ]
