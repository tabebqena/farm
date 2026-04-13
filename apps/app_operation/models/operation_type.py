from django.db import models


class OperationType(models.TextChoices):
    CASH_INJECTION = "CASH_INJECTION", "Cash Injection"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
    PROJECT_FUNDING = "PROJECT_FUNDING", "Project Funding"
    PROJECT_REFUND = "PROJECT_REFUND", "Project Refund"
    PROFIT_DISTRIBUTION = "PROFIT_DISTRIBUTION", "Profit Distribution"
    LOSS_COVERAGE = "LOSS_COVERAGE", "Loss Coverage"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Internal Transfer"
    LOAN = "LOAN", "Loan"
    PURCHASE = "PURCHASE", "Purchase"
    SALE = "SALE", "Sale"
    EXPENSE = "EXPENSE", "EXPENSE"
    CAPITAL_GAIN = "CAPITAL_GAIN", "CAPITAL_GAIN"
    CAPITAL_LOSS = "CAPITAL_LOSS", "CAPITAL_LOSS"
    WORKER_ADVANCE = "WORKER_ADVANCE", "WORKER_ADVANCE"
    CORRECTION_CREDIT = "CORRECTION_CREDIT", "Correction Credit"
    CORRECTION_DEBIT = "CORRECTION_DEBIT", "Correction Debit"
