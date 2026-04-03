from django.db import models


# -----------------------------
# Transaction Types
# -----------------------------
class TransactionType(models.TextChoices):
    # --- Operational ---
    # REVENUE = ("REVENUE", "REVENUE")
    # OTHER_INCOME = ("OTHER_INCOME", "OTHER_INCOME")
    # TAX_PAYMENT = ("TAX_PAYMENT", "TAX_PAYMENT")
    # INVOICE_ADJUSTMENT = ("INVOICE_ADJUSTMENT", "INVOICE_ADJUSTMENT")
    # PAYROLL_ADJUSTMENT = (
    #     "PAYROLL_ADJUSTMENT",
    #     "PAYROLL_ADJUSTMENT",
    # )
    #  purchases
    PURCHASE_ISSUANCE = (
        "PURCHASE_ISSUANCE",
        "PURCHASE_ISSUANCE",
    )
    PURCHASE_PAYMENT = (
        "PURCHASE_PAYMENT",
        "PURCHASE_PAYMENT",
    )
    PURCHASE_ADJUSTMENT = (
        "PURCHASE_ADJUSTMENT",
        "PURCHASE_ADJUSTMENT",
    )
    # The return is a subtype of adjustement, so I will comment.
    # PURCHASE_RETURN = ("PURCHASE_RETURN", "PURCHASE_RETURN")
    # Sale
    SALE_ISSUANCE = (
        "SALE_ISSUANCE",
        "SALE_ISSUANCE",
    )
    # the same of SALE_PAYMENT but with better name
    SALE_COLLECTION = (
        "SALE_COLLECTION",
        "SALE_COLLECTION",
    )
    SALE_ADJUSTMENT = (
        "SALE_ADJUSTMENT",
        "SALE_ADJUSTMENT",
    )
    # Expense
    EXPENSE_ISSUANCE = (
        "EXPENSE_ISSUANCE",
        "EXPENSE_ISSUANCE",
    )
    EXPENSE_PAYMENT = (
        "EXPENSE_PAYMENT",
        "EXPENSE_PAYMENT",
    )
    EXPENSE_ADJUSTMENT = (
        "EXPENSE_ADJUSTMENT",
        "EXPENSE_ADJUSTMENT",
    )

    # --- Workers (Strict 1:1 Pairs) ---
    # WORKER_WAGE = (
    #     "WORKER_WAGE",
    #     "WORKER_WAGE",
    # )
    # SALARY_INCOME = (
    #     "SALARY_INCOME",
    #     "SALARY_INCOME",
    # )  # Mirror of WORKER_WAGE

    WORKER_ADVANCE_ISSUANCE = (
        "WORKER_ADVANCE_ISSUANCE",
        "WORKER_ADVANCE_ISSUANCE",
    )
    WORKER_ADVANCE_PAYMENT = (
        "WORKER_ADVANCE_PAYMENT",
        "WORKER_ADVANCE_PAYMENT",
    )
    # ADVANCE_RECEIPT = (
    #     "ADVANCE_RECEIPT",
    #     "WORKER_ADVANCE",
    # )  # Mirror of WORKER_ADVANCE

    WORKER_ADVANCE_REPAYMENT = (
        "WORKER_ADVANCE_REPAYMENT_PAYEMENT",
        "WORKER_ADVANCE_REPAYMENT_PAYEMENT",
    )
    # ADVANCE_COLLECTION = (
    #     "ADVANCE_COLLECTION",
    #     "ADVANCE_COLLECTION",
    # )  # Mirror of ADVANCE_REPAYMENT

    # --- Capital ---
    CASH_INJECTION_ISSUANCE = (
        "CASH_INJECTION_ISSUANCE",
        "CASH_INJECTION_ISSUANCE",
    )

    CASH_INJECTION_PAYMENT = (
        "CASH_INJECTION_PAYMENT",
        "CASH_INJECTION_PAYMENT",
    )

    CAPITAL_WITHDRAWAL_ISSUANCE = (
        "CAPITAL_WITHDRAWAL_ISSUANCE",
        "CAPITAL_WITHDRAWAL_ISSUANCE",
    )

    CAPITAL_WITHDRAWAL_PAYMENT = (
        "CAPITAL_WITHDRAWAL_PAYMENT",
        "CAPITAL_WITHDRAWAL_PAYMENT",
    )

    CAPITAL_GAIN_ISSUANCE = (
        "CAPITAL_GAIN_ISSUANCE",
        "CAPITAL_GAIN_ISSUANCE",
    )
    CAPITAL_GAIN_PAYMENT = (
        "CAPITAL_GAIN_PAYMENT",
        "CAPITAL_GAIN_PAYMENT",
    )
    CAPITAL_LOSS_ISSUANCE = (
        "CAPITAL_LOSS_ISSUANCE",
        "CAPITAL_LOSS_ISSUANCE",
    )
    CAPITAL_LOSS_PAYMENT = (
        "CAPITAL_LOSS_PAYMENT",
        "CAPITAL_LOSS_PAYMENT",
    )
    LOSS_COVERAGE_ISSUANCE = (
        "LOSS_COVERAGE_ISSUANCE",
        "LOSS_COVERAGE_ISSUANCE",
    )
    LOSS_COVERAGE_PAYMENT = (
        "LOSS_COVERAGE_PAYMENT",
        "LOSS_COVERAGE_PAYMENT",
    )

    PROFIT_DISTRIBUTION_ISSUANCE = (
        "PROFIT_DISTRIBUTION_ISSUANCE",
        "PROFIT_DISTRIBUTION_ISSUANCE",
    )
    PROFIT_DISTRIBUTION_PAYMENT = (
        "PROFIT_DISTRIBUTION_PAYMENT",
        "PROFIT_DISTRIBUTION_PAYMENT",
    )

    # PROFIT_COLLECTION = ("PROFIT_COLLECTION", "PROFIT_COLLECTION")

    # --- Projects ---
    PROJECT_FUNDING_ISSUANCE = (
        "PROJECT_FUNDING_ISSUANCE",
        "PROJECT_FUNDING_ISSUANCE",
    )

    PROJECT_FUNDING_PAYMENT = (
        "PROJECT_FUNDING_PAYMENT",
        "PROJECT_FUNDING_PAYMENT",
    )
    PROJECT_REFUND_ISSUANCE = (
        "PROJECT_REFUND_ISSUANCE",
        "PROJECT_REFUND_ISSUANCE",
    )
    PROJECT_REFUND_PAYMENT = (
        "PROJECT_REFUND_PAYMENT",
        "PROJECT_REFUND_PAYMENT",
    )

    # --- Loans & Debts (Strict 1:1 Pairs) ---
    # LOAN_ISSUANCE = ("LOAN_ISSUANCE", "LOAN_ISSUANCE")  # إصدار قرض للغير
    # LOAN_RECEIVED_BY_OTHER = (
    #     "LOAN_RECEIVED_BY_OTHER",
    #     "LOAN_RECEIVED_BY_OTHER",
    # )  # استلام قرض (عند الطرف الآخر)

    # LOAN_REPAYMENT_BY_OTHER = (
    #     "LOAN_REPAYMENT_BY_OTHER",
    #     "LOAN_REPAYMENT_BY_OTHER",
    # )  # سداد قرض (من الغير)
    # LOAN_RECOVERY = ("LOAN_RECOVERY", "LOAN_RECOVERY")  # استرداد قرض (عندنا)
    LOAN_ISSUANCE = (
        "LOAN_ISSUANCE",
        "LOAN_ISSUANCE",
    )
    LOAN_PAYMENT = (
        "LOAN_PAYMENT",
        "LOAN_PAYMENT",
    )
    LOAN_REPAYMENT = ("LOAN_REPAYMENT", "LOAN_REPAYMENT")
    # DEBT_RECEIVED = ("DEBT_RECEIVED", "DEBT_RECEIVED")  # استلام دين (قرض لنا)
    # DEBT_GIVEN_BY_LENDER = (
    #     "DEBT_GIVEN_BY_LENDER",
    #     "DEBT_GIVEN_BY_LENDER",
    # )  # تقديم دين (عند المقرض)

    # DEBT_SETTLEMENT_BY_LENDER = (
    #     "DEBT_SETTLEMENT_BY_LENDER",
    #     "DEBT_SETTLEMENT_BY_LENDER",
    # )

    # --- Internal ---
    INTERNAL_TRANSFER_ISSUANCE = (
        "INTERNAL_TRANSFER_ISSUANCE",
        "INTERNAL_TRANSFER_ISSUANCE",
    )
    INTERNAL_TRANSFER_PAYMENT = (
        "INTERNAL_TRANSFER_PAYMENT",
        "INTERNAL_TRANSFER_PAYMENT",
    )

    @classmethod
    def payment_types(cls):
        """Transaction types that represent actual cash movement (affect balance)."""
        return frozenset(
            [
                cls.PURCHASE_PAYMENT,
                cls.SALE_COLLECTION,
                cls.EXPENSE_PAYMENT,
                cls.WORKER_ADVANCE_PAYMENT,
                cls.WORKER_ADVANCE_REPAYMENT,
                cls.CASH_INJECTION_PAYMENT,
                cls.CAPITAL_WITHDRAWAL_PAYMENT,
                cls.CAPITAL_GAIN_PAYMENT,
                cls.CAPITAL_LOSS_PAYMENT,
                cls.LOSS_COVERAGE_PAYMENT,
                cls.PROFIT_DISTRIBUTION_PAYMENT,
                cls.PROJECT_FUNDING_PAYMENT,
                cls.PROJECT_REFUND_PAYMENT,
                cls.LOAN_PAYMENT,
                cls.LOAN_REPAYMENT,
                cls.INTERNAL_TRANSFER_PAYMENT,
            ]
        )

    @classmethod
    def issuance_types(cls):
        """Transaction types that represent issuance (obligation/receivable, do not affect balance)."""
        return frozenset(
            [
                cls.PURCHASE_ISSUANCE,
                cls.SALE_ISSUANCE,
                cls.EXPENSE_ISSUANCE,
                cls.WORKER_ADVANCE_ISSUANCE,
                cls.CASH_INJECTION_ISSUANCE,
                cls.CAPITAL_WITHDRAWAL_ISSUANCE,
                cls.CAPITAL_GAIN_ISSUANCE,
                cls.CAPITAL_LOSS_ISSUANCE,
                cls.LOSS_COVERAGE_ISSUANCE,
                cls.PROFIT_DISTRIBUTION_ISSUANCE,
                cls.PROJECT_FUNDING_ISSUANCE,
                cls.PROJECT_REFUND_ISSUANCE,
                cls.LOAN_ISSUANCE,
                cls.INTERNAL_TRANSFER_ISSUANCE,
            ]
        )
