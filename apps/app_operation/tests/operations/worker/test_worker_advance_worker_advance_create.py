from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.app_entity.models import StakeholderRole
from apps.app_operation.models.proxies import WorkerAdvanceOperation
from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.tests.base import (
    BaseOperationTestCase,
    build_worker_advance,
    make_person,
    make_project,
    make_stakeholder,
    make_worker,
)

User = get_user_model()


class WorkerAdvanceCreateTest(BaseOperationTestCase):
    """
    Operation creation: validation, one-shot transactions, and fund balances.

    At creation the operation issues both WORKER_ADVANCE_ISSUANCE and
    WORKER_ADVANCE_PAYMENT in one atomic step (one-shot pattern).
    """

    amount = Decimal("1000.00")

    def setUp(self):
        super().setUp()
        self.worker = make_worker(self.project, "Ali Worker")

    def _make_op(self, **kwargs):
        # Pull amount/officer overrides out so they are not passed twice
        # (positionally and via **kwargs).
        amount = kwargs.pop("amount", self.amount)
        officer = kwargs.pop("officer", self.officer)
        return build_worker_advance(self.project, self.worker, officer, amount, **kwargs)

    # ------------------------------------------------------------------
    # SE2 — one-shot transaction creation
    # ------------------------------------------------------------------

    def test_create_creates_issuance_tx_exact(self):
        """Exactly one WORKER_ADVANCE_ISSUANCE, project -> worker, amount exact."""
        op = self._make_op()
        op.save()

        self.assert_tx(
            op,
            TransactionType.WORKER_ADVANCE_ISSUANCE,
            self.project,
            self.worker,
            self.amount,
        )

    def test_create_creates_payment_tx_exact(self):
        """Exactly one WORKER_ADVANCE_PAYMENT, project -> worker, amount exact."""
        op = self._make_op()
        op.save()

        self.assert_tx(
            op,
            TransactionType.WORKER_ADVANCE_PAYMENT,
            self.project,
            self.worker,
            self.amount,
        )

    def test_create_creates_exactly_two_transactions(self):
        """The one-shot pattern writes issuance + payment, nothing else."""
        op = self._make_op()
        op.save()

        self.assert_tx_types(
            op,
            {
                TransactionType.WORKER_ADVANCE_ISSUANCE: 1,
                TransactionType.WORKER_ADVANCE_PAYMENT: 1,
            },
        )

    # ------------------------------------------------------------------
    # SE3 — fund balances
    # ------------------------------------------------------------------

    def test_create_project_balance_decreases(self):
        """The project fund loses the advance amount (payment is outgoing)."""
        self._make_op().save()

        self.assert_balance(
            self.project, self.project_funding - self.amount, msg="project"
        )

    def test_create_worker_balance_increases(self):
        """The worker fund gains the advance amount (payment is incoming)."""
        self._make_op().save()

        self.assert_balance(self.worker, self.amount, msg="worker")

    # ------------------------------------------------------------------
    # SE4 — payables / receivables
    # ------------------------------------------------------------------

    def test_create_project_receivables_increase(self):
        """The advance is a receivable the project is owed by the worker."""
        self._make_op().save()

        self.assert_receivables(self.project, self.amount, msg="project")

    def test_create_worker_payables_increase(self):
        """The worker now owes the advance back to the project."""
        self._make_op().save()

        self.assert_payables(self.worker, self.amount, msg="worker")

    def test_create_project_payables_unchanged(self):
        """The advance does not create a payable for the project."""
        self._make_op().save()

        self.assert_payables(self.project, Decimal("0.00"), msg="project")

    def test_create_worker_receivables_unchanged(self):
        """The advance does not create a receivable for the worker."""
        self._make_op().save()

        self.assert_receivables(self.worker, Decimal("0.00"), msg="worker")

    # ------------------------------------------------------------------
    # SE8 — derived repayment amount
    # ------------------------------------------------------------------

    def test_create_remaining_to_repay_equals_amount(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.amount_remaining_to_repay, self.amount)

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_one_shot_prevents_additional_payment_transaction(self):
        op = self._make_op()
        op.save()

        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer,
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_must_be_a_project_entity(self):
        non_project = make_person("Not A Project")
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project.active = False
        self.project.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_insufficient_balance_raises_validation_error(self):
        op = self._make_op(amount=Decimal("99999.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_a_person_entity(self):
        # clean_destination checks destination.person first, before any stakeholder check
        other_project = make_project("Other Project")
        op = self._make_op(destination=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active(self):
        self.worker.active = False
        self.worker.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_without_stakeholder_relationship_raises_validation_error(self):
        unrelated_person = make_person("Unrelated Person")
        op = self._make_op(destination=unrelated_person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        another_worker = make_person("Inactive Worker")
        make_stakeholder(self.project, another_worker, active=False)

        op = self._make_op(destination=another_worker)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_worker_role_stakeholder(self):
        """A person with a non-WORKER stakeholder role should not be a valid destination."""
        non_worker = make_person("Client Person")
        make_stakeholder(self.project, non_worker, role=StakeholderRole.CLIENT)

        op = self._make_op(destination=non_worker)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Amount validation
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        op = self._make_op(amount=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_negative_raises_validation_error(self):
        op = self._make_op(amount=Decimal("-500.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        op = self._make_op(officer=non_staff_user)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer.is_active = False
        self.officer.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_project = make_project("Other Project")
        op.source = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_worker = make_person("Other Worker")
        make_stakeholder(self.project, other_worker)
        op.destination = other_worker
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Balance is enforced by clean() at creation; no per-payment gate needed."""
        self.assertFalse(WorkerAdvanceOperation.check_balance_on_payment)
