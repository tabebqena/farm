from django.db import models


# -----------------------------
# Transaction Types
# -----------------------------
class TransactionType(models.TextChoices):
    # --- Operational ---

    # Source: Project | Destination: Vendor
    # Flow: Project records an obligation to pay a vendor.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    PURCHASE_ISSUANCE = ("PURCHASE_ISSUANCE", "PURCHASE_ISSUANCE")

    # Source: Project | Destination: Vendor
    # Flow: Actual cash moves from project fund to vendor fund.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    PURCHASE_PAYMENT = ("PURCHASE_PAYMENT", "PURCHASE_PAYMENT")

    # Source: Project | Destination: Vendor
    # Flow: Post-invoice increase in what we owe (same direction as Purchase). No cash movement.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    PURCHASE_ADJUSTMENT_INCREASE = (
        "PURCHASE_ADJUSTMENT_INCREASE",
        "PURCHASE_ADJUSTMENT_INCREASE",
    )

    # Source: Vendor | Destination: Project
    # Flow: Vendor reduces what project owes — discount, return, or overcharge correction.
    # No cash movement.
    # Source balance: No change.
    # Source receivables: Decrease  (vendor had a receivable from project; this reduces it)
    # Source payables: None
    PURCHASE_ADJUSTMENT_DECREASE = (
        "PURCHASE_ADJUSTMENT_DECREASE",
        "PURCHASE_ADJUSTMENT_DECREASE",
    )

    # Source: Client | Destination: Project
    # Flow: Client records an obligation to pay the project.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    SALE_ISSUANCE = ("SALE_ISSUANCE", "SALE_ISSUANCE")

    # Source: Client | Destination: Project
    # Flow: Actual cash moves from client fund to project fund.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    SALE_COLLECTION = ("SALE_COLLECTION", "SALE_COLLECTION")

    # Source: Client | Destination: Project
    # Flow: Post-invoice increase in what client owes (same direction as Sale). No cash movement.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    SALE_ADJUSTMENT_INCREASE = ("SALE_ADJUSTMENT_INCREASE", "SALE_ADJUSTMENT_INCREASE")

    # Source: Project | Destination: Client
    # Flow: Project returns value to client — reversed direction (discount, return, overcharge). No cash movement.
    # Source receivables: Decrease
    # Source payables: None
    SALE_ADJUSTMENT_DECREASE = ("SALE_ADJUSTMENT_DECREASE", "SALE_ADJUSTMENT_DECREASE")

    # Source: Project | Destination: World
    # Flow: Project records obligation to the external world.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    EXPENSE_ISSUANCE = ("EXPENSE_ISSUANCE", "EXPENSE_ISSUANCE")

    # Source: Project | Destination: World
    # Flow: Actual cash moves from project to external world.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    EXPENSE_PAYMENT = ("EXPENSE_PAYMENT", "EXPENSE_PAYMENT")

    # Source: Project | Destination: World
    # Flow: Post-issuance increase in expense obligation (same direction as Expense). No cash movement.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    EXPENSE_ADJUSTMENT_INCREASE = (
        "EXPENSE_ADJUSTMENT_INCREASE",
        "EXPENSE_ADJUSTMENT_INCREASE",
    )

    # Source: World | Destination: Project
    # Flow: External world reduces what project owes — rebate, return, or overcharge correction. No cash movement.
    # Source receivables: Decrease  (world had a receivable from project; this reduces it)
    # Source payables: None
    EXPENSE_ADJUSTMENT_DECREASE = (
        "EXPENSE_ADJUSTMENT_DECREASE",
        "EXPENSE_ADJUSTMENT_DECREASE",
    )

    # --- Workers ---
    # Source: Project | Destination: Worker
    # Flow: Memo recording an upcoming advance obligation.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    WORKER_ADVANCE_ISSUANCE = ("WORKER_ADVANCE_ISSUANCE", "WORKER_ADVANCE_ISSUANCE")

    # Source: Project | Destination: Worker
    # Flow: Cash moves from project to worker (creating a receivable).
    # Source balance: Decreases.
    # Source receivables: Increase
    # Source payables: None
    WORKER_ADVANCE_PAYMENT = ("WORKER_ADVANCE_PAYMENT", "WORKER_ADVANCE_PAYMENT")

    # Source: Worker | Destination: Project
    # Flow: Cash moves from worker back to project fund.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease  (worker's debt/obligation to project is cleared)
    WORKER_ADVANCE_REPAYMENT = (
        "WORKER_ADVANCE_REPAYMENT",
        "WORKER_ADVANCE_REPAYMENT",
    )

    # --- Capital ---
    # Source: World | Destination: Person
    # Flow: Commitment of capital from external source.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CASH_INJECTION_ISSUANCE = ("CASH_INJECTION_ISSUANCE", "CASH_INJECTION_ISSUANCE")

    # Source: World | Destination: Person
    # Flow: Actual cash inflow into the person fund.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CASH_INJECTION_PAYMENT = ("CASH_INJECTION_PAYMENT", "CASH_INJECTION_PAYMENT")

    # Source: Person | Destination: World
    # Flow: Request to move capital out of the person.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CAPITAL_WITHDRAWAL_ISSUANCE = (
        "CAPITAL_WITHDRAWAL_ISSUANCE",
        "CAPITAL_WITHDRAWAL_ISSUANCE",
    )

    # Source: Person | Destination: World
    # Flow: Actual cash outflow from person to world.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CAPITAL_WITHDRAWAL_PAYMENT = (
        "CAPITAL_WITHDRAWAL_PAYMENT",
        "CAPITAL_WITHDRAWAL_PAYMENT",
    )

    # Source: System | Destination: Project
    # Flow: Virtual value creation from the system to the project.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CAPITAL_GAIN_ISSUANCE = ("CAPITAL_GAIN_ISSUANCE", "CAPITAL_GAIN_ISSUANCE")

    # Source: System | Destination: Project
    # Flow: Realization of virtual value (increases the inventory value ).
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CAPITAL_GAIN_PAYMENT = ("CAPITAL_GAIN_PAYMENT", "CAPITAL_GAIN_PAYMENT")

    # Source: Project | Destination: System
    # Flow: Virtual value loss flowing from project to system.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CAPITAL_LOSS_ISSUANCE = ("CAPITAL_LOSS_ISSUANCE", "CAPITAL_LOSS_ISSUANCE")

    # Source: Project | Destination: System
    # Flow: Realization of virtual loss (decreases inventory value ).
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CAPITAL_LOSS_PAYMENT = ("CAPITAL_LOSS_PAYMENT", "CAPITAL_LOSS_PAYMENT")

    # Source: Person | Destination: Project
    # Flow: Obligation for stakeholder to cover a project loss.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    LOSS_COVERAGE_ISSUANCE = ("LOSS_COVERAGE_ISSUANCE", "LOSS_COVERAGE_ISSUANCE")

    # Source: Person | Destination: Project
    # Flow: Cash received from stakeholder to restore project balance.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    LOSS_COVERAGE_PAYMENT = ("LOSS_COVERAGE_PAYMENT", "LOSS_COVERAGE_PAYMENT")

    # Source: Project | Destination: Person
    # Flow: Declared profit flowing toward shareholders.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    PROFIT_DISTRIBUTION_ISSUANCE = (
        "PROFIT_DISTRIBUTION_ISSUANCE",
        "PROFIT_DISTRIBUTION_ISSUANCE",
    )

    # Source: Project | Destination: Person
    # Flow: Actual cash payment of profit to shareholders.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    PROFIT_DISTRIBUTION_PAYMENT = (
        "PROFIT_DISTRIBUTION_PAYMENT",
        "PROFIT_DISTRIBUTION_PAYMENT",
    )

    # --- Projects ---
    # Source: Person | Destination: Project
    # Flow: Allocation of budget to a project.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    PROJECT_FUNDING_ISSUANCE = ("PROJECT_FUNDING_ISSUANCE", "PROJECT_FUNDING_ISSUANCE")

    # Source: Person | Destination: Project
    # Flow: Actual transfer of funds into project.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    PROJECT_FUNDING_PAYMENT = ("PROJECT_FUNDING_PAYMENT", "PROJECT_FUNDING_PAYMENT")

    # Source: Project | Destination: Person
    # Flow: Allocation of unused project funds to be returned.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: Increase
    PROJECT_REFUND_ISSUANCE = ("PROJECT_REFUND_ISSUANCE", "PROJECT_REFUND_ISSUANCE")

    # Source: Project | Destination: Person
    # Flow: Actual cash movement returning funds from project.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    PROJECT_REFUND_PAYMENT = ("PROJECT_REFUND_PAYMENT", "PROJECT_REFUND_PAYMENT")

    # --- Loans & Debts ---
    # Source: Creditor(Person/Project) | Destination: Debtor(Person/Project)
    # Flow: Memo of loan agreement.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    LOAN_ISSUANCE = ("LOAN_ISSUANCE", "LOAN_ISSUANCE")

    # Source: Creditor (Person/Project) | Destination: Debtor (Person/Project)
    # Flow: Disbursement of cash from lender to borrower.
    # Source balance: Decreases.
    # Source receivables: Increase
    # Source payables: None
    LOAN_PAYMENT = ("LOAN_PAYMENT", "LOAN_PAYMENT")

    # Source: Debtor (Person/Project) | Destination: Creditor (Person/Project)
    # Flow: Return of cash from borrower to lender.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: Decrease
    LOAN_REPAYMENT = ("LOAN_REPAYMENT", "LOAN_REPAYMENT")

    # --- Birth / Death (asset creation & removal, no cash flow) ---
    # Source: System | Destination: Project
    # Flow: Virtual creation of asset value from the system.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    BIRTH_ISSUANCE = ("BIRTH_ISSUANCE", "BIRTH_ISSUANCE")

    # Source: System | Destination: Project
    # Flow: Virtual cash flow to increase project valuation.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    BIRTH_PAYMENT = ("BIRTH_PAYMENT", "BIRTH_PAYMENT")

    # Source: Project | Destination: System
    # Flow: Virtual removal of asset value to the system.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    DEATH_ISSUANCE = ("DEATH_ISSUANCE", "DEATH_ISSUANCE")

    # Source: Project | Destination: System
    # Flow: Virtual cash flow to decrease project valuation.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    DEATH_PAYMENT = ("DEATH_PAYMENT", "DEATH_PAYMENT")

    # --- Consumption ---
    # Source: Project | Destination: System
    # Flow: Recording the usage of an asset.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CONSUMPTION_ISSUANCE = ("CONSUMPTION_ISSUANCE", "CONSUMPTION_ISSUANCE")

    # Source: Project | Destination: System
    # Flow: Virtual cost booking (decreases project valuation).
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CONSUMPTION_PAYMENT = ("CONSUMPTION_PAYMENT", "CONSUMPTION_PAYMENT")

    # --- Corrections ---
    # Source: System | Destination: Project
    # Flow: Administrative memo to increase project balance.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CORRECTION_CREDIT_ISSUANCE = (
        "CORRECTION_CREDIT_ISSUANCE",
        "CORRECTION_CREDIT_ISSUANCE",
    )

    # Source: System | Destination: Project
    # Flow: Direct virtual cash inflow for balance adjustment.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CORRECTION_CREDIT_PAYMENT = (
        "CORRECTION_CREDIT_PAYMENT",
        "CORRECTION_CREDIT_PAYMENT",
    )

    # Source: Project | Destination: System
    # Flow: Administrative memo to decrease project balance.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    CORRECTION_DEBIT_ISSUANCE = (
        "CORRECTION_DEBIT_ISSUANCE",
        "CORRECTION_DEBIT_ISSUANCE",
    )

    # Source: Project | Destination: System
    # Flow: Direct virtual cash outflow for balance adjustment.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    CORRECTION_DEBIT_PAYMENT = ("CORRECTION_DEBIT_PAYMENT", "CORRECTION_DEBIT_PAYMENT")

    # --- Internal ---
    # Source: Fund A | Destination: Fund B
    # Flow: Request to move cash between internal project funds.
    # Source balance: No change.
    # Source receivables: None
    # Source payables: None
    INTERNAL_TRANSFER_ISSUANCE = (
        "INTERNAL_TRANSFER_ISSUANCE",
        "INTERNAL_TRANSFER_ISSUANCE",
    )

    # Source: Fund A | Destination: Fund B
    # Flow: Actual cash movement within the project/system.
    # Source balance: Decreases.
    # Source receivables: None
    # Source payables: None
    INTERNAL_TRANSFER_PAYMENT = (
        "INTERNAL_TRANSFER_PAYMENT",
        "INTERNAL_TRANSFER_PAYMENT",
    )

    def is_allowed_entity_types(self, source, dest) -> bool:
        return self.get_entity_type_violation(source, dest) is None

    def get_entity_type_violation(self, source, dest) -> str | None:
        allowed = _TX_ENTITY_TYPE_MAP.get(self)
        if allowed is None:
            return None
        source_check, dest_check = allowed
        source_ok = source_check(source)
        dest_ok = dest_check(dest)
        if source_ok and dest_ok:
            return None
        parts = []
        if not source_ok:
            parts.append(
                f"source '{source}' (entity_type={source.entity_type})"
                f" must be {source_check.__name__}"
            )
        if not dest_ok:
            parts.append(
                f"target '{dest}' (entity_type={dest.entity_type})"
                f" must be {dest_check.__name__}"
            )
        return "; ".join(parts)

    def is_allowed_operation_type(self, document) -> bool:
        allowed = _TX_OPERATION_MAP.get(self)
        if allowed is None:
            return True
        # Operation proxies expose operation_type directly;
        # Adjustment exposes it via its parent operation.
        op_type = getattr(document, "operation_type", None) or getattr(
            getattr(document, "operation", None), "operation_type", None
        )
        return op_type in allowed

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
                cls.CORRECTION_CREDIT_PAYMENT,
                cls.CORRECTION_DEBIT_PAYMENT,
                cls.BIRTH_PAYMENT,
                cls.DEATH_PAYMENT,
                cls.CONSUMPTION_PAYMENT,
            ]
        )

    @classmethod
    def issuance_types(cls):
        """Transaction types that represent issuance (obligation/receivable, do not affect balance)."""
        return frozenset(
            [
                cls.PURCHASE_ISSUANCE,
                cls.PURCHASE_ADJUSTMENT_INCREASE,
                cls.PURCHASE_ADJUSTMENT_DECREASE,
                cls.SALE_ISSUANCE,
                cls.SALE_ADJUSTMENT_INCREASE,
                cls.SALE_ADJUSTMENT_DECREASE,
                cls.EXPENSE_ISSUANCE,
                cls.EXPENSE_ADJUSTMENT_INCREASE,
                cls.EXPENSE_ADJUSTMENT_DECREASE,
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
                cls.CORRECTION_CREDIT_ISSUANCE,
                cls.CORRECTION_DEBIT_ISSUANCE,
                cls.BIRTH_ISSUANCE,
                cls.DEATH_ISSUANCE,
                cls.CONSUMPTION_ISSUANCE,
            ]
        )


def _named(fn, name):
    fn.__name__ = name
    return fn


def _build_tx_entity_type_map():
    T = TransactionType
    is_project = _named(lambda e: e.is_project, "project")
    is_person = _named(lambda e: e.is_person, "person")
    is_system = _named(lambda e: e.is_system, "system")
    is_world = _named(lambda e: e.is_world, "world")
    is_vendor = _named(lambda e: e.is_vendor, "vendor")
    is_client = _named(lambda e: e.is_client, "client")
    is_worker = _named(lambda e: e.is_worker, "worker")
    is_shareholder = _named(lambda e: e.is_shareholder, "shareholder")
    not_virtual = _named(lambda e: not e.is_virtual, "non-virtual")
    return {
        # Purchase: project pays a vendor
        T.PURCHASE_ISSUANCE: (is_project, is_vendor),
        T.PURCHASE_PAYMENT: (is_project, is_vendor),
        T.PURCHASE_ADJUSTMENT_INCREASE: (is_project, is_vendor),
        T.PURCHASE_ADJUSTMENT_DECREASE: (is_vendor, is_project),
        # Sale: client owes the project
        T.SALE_ISSUANCE: (is_client, is_project),
        T.SALE_COLLECTION: (is_client, is_project),
        T.SALE_ADJUSTMENT_INCREASE: (is_client, is_project),
        T.SALE_ADJUSTMENT_DECREASE: (is_project, is_client),
        # Expense: project → world
        T.EXPENSE_ISSUANCE: (is_project, is_world),
        T.EXPENSE_PAYMENT: (is_project, is_world),
        T.EXPENSE_ADJUSTMENT_INCREASE: (is_project, is_world),
        T.EXPENSE_ADJUSTMENT_DECREASE: (is_world, is_project),
        # Worker advance: project → worker
        T.WORKER_ADVANCE_ISSUANCE: (is_project, is_worker),
        T.WORKER_ADVANCE_PAYMENT: (is_project, is_worker),
        T.WORKER_ADVANCE_REPAYMENT: (is_worker, is_project),
        # Capital injection: world → person
        T.CASH_INJECTION_ISSUANCE: (is_world, is_person),
        T.CASH_INJECTION_PAYMENT: (is_world, is_person),
        # Capital withdrawal: person → world
        T.CAPITAL_WITHDRAWAL_ISSUANCE: (is_person, is_world),
        T.CAPITAL_WITHDRAWAL_PAYMENT: (is_person, is_world),
        # Capital gain/loss: system ↔ project
        T.CAPITAL_GAIN_ISSUANCE: (is_system, is_project),
        T.CAPITAL_GAIN_PAYMENT: (is_system, is_project),
        T.CAPITAL_LOSS_ISSUANCE: (is_project, is_system),
        T.CAPITAL_LOSS_PAYMENT: (is_project, is_system),
        # Loss coverage: shareholder → project
        T.LOSS_COVERAGE_ISSUANCE: (is_shareholder, is_project),
        T.LOSS_COVERAGE_PAYMENT: (is_shareholder, is_project),
        # Profit distribution: project → shareholder
        T.PROFIT_DISTRIBUTION_ISSUANCE: (is_project, is_shareholder),
        T.PROFIT_DISTRIBUTION_PAYMENT: (is_project, is_shareholder),
        # Project funding/refund: shareholder ↔ project
        T.PROJECT_FUNDING_ISSUANCE: (is_shareholder, is_project),
        T.PROJECT_FUNDING_PAYMENT: (is_shareholder, is_project),
        T.PROJECT_REFUND_ISSUANCE: (is_project, is_shareholder),
        T.PROJECT_REFUND_PAYMENT: (is_project, is_shareholder),
        # Loans: any non-virtual entity on both sides
        T.LOAN_ISSUANCE: (not_virtual, not_virtual),
        T.LOAN_PAYMENT: (not_virtual, not_virtual),
        T.LOAN_REPAYMENT: (not_virtual, not_virtual),
        # Birth/death: system ↔ project
        T.BIRTH_ISSUANCE: (is_system, is_project),
        T.BIRTH_PAYMENT: (is_system, is_project),
        T.DEATH_ISSUANCE: (is_project, is_system),
        T.DEATH_PAYMENT: (is_project, is_system),
        # Consumption: project → system
        T.CONSUMPTION_ISSUANCE: (is_project, is_system),
        T.CONSUMPTION_PAYMENT: (is_project, is_system),
        # Corrections: system ↔ project
        T.CORRECTION_CREDIT_ISSUANCE: (is_system, is_project),
        T.CORRECTION_CREDIT_PAYMENT: (is_system, is_project),
        T.CORRECTION_DEBIT_ISSUANCE: (is_project, is_system),
        T.CORRECTION_DEBIT_PAYMENT: (is_project, is_system),
        # Internal transfer: any non-virtual entity on both sides
        T.INTERNAL_TRANSFER_ISSUANCE: (not_virtual, not_virtual),
        T.INTERNAL_TRANSFER_PAYMENT: (not_virtual, not_virtual),
    }


_TX_ENTITY_TYPE_MAP = _build_tx_entity_type_map()


def _build_tx_operation_map():
    from apps.app_operation.models.operation_type import OperationType as OT

    T = TransactionType
    Purchase = frozenset({OT.PURCHASE})
    Sale = frozenset({OT.SALE})
    Expense = frozenset({OT.EXPENSE})
    # Adjustments carry the parent operation_type (PURCHASE/SALE/EXPENSE),
    # resolved via document.operation.operation_type in is_allowed_operation_type.
    AdjPurchase = frozenset({OT.PURCHASE})
    AdjSale = frozenset({OT.SALE})
    AdjExpense = frozenset({OT.EXPENSE})
    WorkerAdv = frozenset({OT.WORKER_ADVANCE})
    CashInj = frozenset({OT.CASH_INJECTION})
    CashWith = frozenset({OT.CASH_WITHDRAWAL})
    CapGain = frozenset({OT.CAPITAL_GAIN})
    CapLoss = frozenset({OT.CAPITAL_LOSS})
    LossCov = frozenset({OT.LOSS_COVERAGE})
    ProfDist = frozenset({OT.PROFIT_DISTRIBUTION})
    ProjFund = frozenset({OT.PROJECT_FUNDING})
    ProjRef = frozenset({OT.PROJECT_REFUND})
    Loan = frozenset({OT.LOAN})
    Birth = frozenset({OT.BIRTH})
    Death = frozenset({OT.DEATH})
    Consump = frozenset({OT.CONSUMPTION})
    CorrCr = frozenset({OT.CORRECTION_CREDIT})
    CorrDb = frozenset({OT.CORRECTION_DEBIT})
    IntTr = frozenset({OT.INTERNAL_TRANSFER})
    return {
        T.PURCHASE_ISSUANCE: Purchase,
        T.PURCHASE_PAYMENT: Purchase,
        T.PURCHASE_ADJUSTMENT_INCREASE: AdjPurchase,
        T.PURCHASE_ADJUSTMENT_DECREASE: AdjPurchase,
        T.SALE_ISSUANCE: Sale,
        T.SALE_COLLECTION: Sale,
        T.SALE_ADJUSTMENT_INCREASE: AdjSale,
        T.SALE_ADJUSTMENT_DECREASE: AdjSale,
        T.EXPENSE_ISSUANCE: Expense,
        T.EXPENSE_PAYMENT: Expense,
        T.EXPENSE_ADJUSTMENT_INCREASE: AdjExpense,
        T.EXPENSE_ADJUSTMENT_DECREASE: AdjExpense,
        T.WORKER_ADVANCE_ISSUANCE: WorkerAdv,
        T.WORKER_ADVANCE_PAYMENT: WorkerAdv,
        T.WORKER_ADVANCE_REPAYMENT: WorkerAdv,
        T.CASH_INJECTION_ISSUANCE: CashInj,
        T.CASH_INJECTION_PAYMENT: CashInj,
        T.CAPITAL_WITHDRAWAL_ISSUANCE: CashWith,
        T.CAPITAL_WITHDRAWAL_PAYMENT: CashWith,
        T.CAPITAL_GAIN_ISSUANCE: CapGain,
        T.CAPITAL_GAIN_PAYMENT: CapGain,
        T.CAPITAL_LOSS_ISSUANCE: CapLoss,
        T.CAPITAL_LOSS_PAYMENT: CapLoss,
        T.LOSS_COVERAGE_ISSUANCE: LossCov,
        T.LOSS_COVERAGE_PAYMENT: LossCov,
        T.PROFIT_DISTRIBUTION_ISSUANCE: ProfDist,
        T.PROFIT_DISTRIBUTION_PAYMENT: ProfDist,
        T.PROJECT_FUNDING_ISSUANCE: ProjFund,
        T.PROJECT_FUNDING_PAYMENT: ProjFund,
        T.PROJECT_REFUND_ISSUANCE: ProjRef,
        T.PROJECT_REFUND_PAYMENT: ProjRef,
        T.LOAN_ISSUANCE: Loan,
        T.LOAN_PAYMENT: Loan,
        T.LOAN_REPAYMENT: Loan,
        T.BIRTH_ISSUANCE: Birth,
        T.BIRTH_PAYMENT: Birth,
        T.DEATH_ISSUANCE: Death,
        T.DEATH_PAYMENT: Death,
        T.CONSUMPTION_ISSUANCE: Consump,
        T.CONSUMPTION_PAYMENT: Consump,
        T.CORRECTION_CREDIT_ISSUANCE: CorrCr,
        T.CORRECTION_CREDIT_PAYMENT: CorrCr,
        T.CORRECTION_DEBIT_ISSUANCE: CorrDb,
        T.CORRECTION_DEBIT_PAYMENT: CorrDb,
        T.INTERNAL_TRANSFER_ISSUANCE: IntTr,
        T.INTERNAL_TRANSFER_PAYMENT: IntTr,
    }


_TX_OPERATION_MAP = _build_tx_operation_map()
