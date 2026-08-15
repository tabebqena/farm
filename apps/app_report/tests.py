from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine
from apps.app_inventory.tests.general import (
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
    make_person_entity,
    make_project_entity,
    make_user,
)
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType

from . import reporting


class ReportBaseTestCase(TestCase):
    """Shared world: world / project / person / client / vendor + an officer."""

    @classmethod
    def setUpTestData(cls):
        cls.officer = make_user(username="report_officer", is_staff=True)
        cls.world = Entity.create(EntityType.WORLD)
        cls.project = make_project_entity("Farm Project")
        cls.person = make_person_entity("Ali Person")
        cls.client_entity = make_person_entity("Client Person", is_client=True)
        cls.vendor = make_person_entity("Vendor Person", is_vendor=True)
        cls.project_period = cls.project.financial_periods.get(end_date__isnull=True)
        cls.person_period = cls.person.financial_periods.get(end_date__isnull=True)

    def _tx(self, source, target, tx_type, amount, *, date=None, reversal_of=None):
        return Transaction.objects.create(
            source=source,
            target=target,
            type=tx_type,
            amount=Decimal(str(amount)),
            officer=self.officer,
            description="report test tx",
            date=date or timezone.now(),
            document=self.project,
            reversal_of=reversal_of,
        )


class IncomeStatementReportingTest(ReportBaseTestCase):
    def test_income_and_costs_buckets(self):
        self._tx(self.client_entity, self.project, TransactionType.SALE_ISSUANCE, "100.00")
        self._tx(self.project, self.vendor, TransactionType.PURCHASE_ISSUANCE, "60.00")
        self._tx(self.project, self.world, TransactionType.EXPENSE_ISSUANCE, "20.00")

        stmt = reporting.income_statement(self.project_period)
        self.assertEqual(stmt["income_total"], Decimal("100.00"))
        self.assertEqual(stmt["costs_total"], Decimal("80.00"))
        self.assertEqual(stmt["net"], Decimal("20.00"))
        self.assertEqual(stmt["income"][TransactionType.SALE_ISSUANCE], Decimal("100.00"))
        self.assertEqual(stmt["costs"][TransactionType.PURCHASE_ISSUANCE], Decimal("60.00"))
        self.assertEqual(stmt["costs"][TransactionType.EXPENSE_ISSUANCE], Decimal("20.00"))
        # The helper must stay consistent with the model contract.
        self.assertEqual(stmt["net"], self.project.profit_loss(self.project_period))

    def test_reversal_keeps_consistency_with_model(self):
        original = self._tx(
            self.client_entity, self.project, TransactionType.SALE_ISSUANCE, "100.00"
        )
        self._tx(
            self.project,
            self.client_entity,
            TransactionType.SALE_ISSUANCE,
            "100.00",
            reversal_of=original,
        )
        stmt = reporting.income_statement(self.project_period)
        self.assertEqual(stmt["net"], self.project.profit_loss(self.project_period))


class BalanceSheetReportingTest(ReportBaseTestCase):
    def test_reconciliation(self):
        self._tx(self.person, self.project, TransactionType.PROJECT_FUNDING_PAYMENT, "1000.00")
        self._tx(self.project, self.vendor, TransactionType.PURCHASE_ISSUANCE, "300.00")
        self._tx(self.client_entity, self.project, TransactionType.SALE_ISSUANCE, "200.00")

        stmt = reporting.balance_sheet(self.project_period)
        self.assertEqual(stmt["cash"], Decimal("1000.00"))
        self.assertEqual(stmt["receivables"], Decimal("200.00"))
        self.assertEqual(stmt["inventory"], Decimal("0.00"))
        self.assertEqual(stmt["payables"], Decimal("300.00"))
        self.assertEqual(stmt["assets"], Decimal("1200.00"))
        self.assertEqual(stmt["liabilities"], Decimal("300.00"))
        self.assertEqual(stmt["equity"], Decimal("900.00"))
        self.assertEqual(stmt["equity"], stmt["assets"] - stmt["liabilities"])

    def test_inventory_included_in_assets(self):
        template = make_product_template("Calves")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        op = make_operation(self.project, self.vendor, self.officer)
        item = make_invoice_item(op, template, Decimal("5"), Decimal("100"))
        product = make_product(template, unit_price=Decimal("100"), quantity=5, entity=self.project)
        InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=Decimal("5"),
            date=date.today(),
            officer=self.officer,
        )
        stmt = reporting.balance_sheet(self.project_period)
        self.assertEqual(stmt["inventory"], Decimal("500.00"))
        self.assertEqual(stmt["assets"], stmt["cash"] + stmt["receivables"] + stmt["inventory"])


class CashFlowReportingTest(ReportBaseTestCase):
    def test_activity_split(self):
        self._tx(self.person, self.project, TransactionType.PROJECT_FUNDING_PAYMENT, "1000.00")
        self._tx(self.project, self.vendor, TransactionType.PURCHASE_PAYMENT, "300.00")

        stmt = reporting.cash_flow(self.project_period)
        self.assertEqual(stmt["opening"], Decimal("0.00"))
        self.assertEqual(stmt["operating"]["in"], Decimal("0.00"))
        self.assertEqual(stmt["operating"]["out"], Decimal("300.00"))
        self.assertEqual(stmt["operating"]["net"], Decimal("-300.00"))
        self.assertEqual(stmt["financing"]["in"], Decimal("1000.00"))
        self.assertEqual(stmt["financing"]["net"], Decimal("1000.00"))
        self.assertEqual(stmt["investing"]["net"], Decimal("0.00"))
        self.assertEqual(stmt["closing"], Decimal("700.00"))
        self.assertEqual(stmt["closing"], self.project.balance)


class EquityReportingTest(ReportBaseTestCase):
    def test_person_equity(self):
        self._tx(self.world, self.person, TransactionType.CASH_INJECTION_PAYMENT, "500.00")
        self._tx(self.person, self.world, TransactionType.CAPITAL_WITHDRAWAL_PAYMENT, "100.00")

        stmt = reporting.equity(self.person_period)
        self.assertFalse(stmt["is_project"])
        self.assertEqual(stmt["opening"], Decimal("0.00"))
        self.assertEqual(stmt["contributions"], Decimal("500.00"))
        self.assertEqual(stmt["withdrawals"], Decimal("100.00"))
        self.assertEqual(stmt["closing"], Decimal("400.00"))
        self.assertEqual(stmt["closing"], self.person.balance)

    def test_project_equity(self):
        self._tx(self.person, self.project, TransactionType.PROJECT_FUNDING_PAYMENT, "1000.00")
        self._tx(self.project, self.person, TransactionType.PROJECT_REFUND_ISSUANCE, "200.00")
        self._tx(self.project, self.person, TransactionType.PROJECT_REFUND_PAYMENT, "200.00")

        stmt = reporting.equity(self.project_period)
        self.assertTrue(stmt["is_project"])
        self.assertEqual(stmt["opening"], Decimal("0.00"))
        self.assertEqual(stmt["contributed_capital"], Decimal("800.00"))
        self.assertEqual(stmt["retained_earnings"], Decimal("0.00"))
        self.assertEqual(stmt["closing"], Decimal("800.00"))
        self.assertEqual(
            stmt["closing"],
            reporting.balance_sheet(self.project_period)["equity"],
        )


class ReportsHubViewTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)

    def test_project_hub_lists_all_statements(self):
        resp = self.client.get(reverse("report_hub", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Income Statement")
        self.assertContains(resp, "Balance Sheet")
        self.assertContains(resp, "Cash Flow")
        self.assertContains(resp, "Equity")

    def test_person_hub_lists_only_person_reports(self):
        resp = self.client.get(reverse("report_hub", args=[self.person.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cash Flow")
        self.assertNotContains(resp, "Income Statement")
        self.assertNotContains(resp, "Balance Sheet")

    def test_missing_entity_returns_404(self):
        resp = self.client.get(reverse("report_hub", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse("report_hub", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 302)


class IncomeStatementViewTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)
        self._tx(self.client_entity, self.project, TransactionType.SALE_ISSUANCE, "100.00")

    def test_project_income_statement_renders(self):
        resp = self.client.get(reverse("income_statement", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["statement"]["net"], Decimal("100.00"))
        self.assertContains(resp, "Net Profit / (Loss)")

    def test_person_income_statement_forbidden(self):
        resp = self.client.get(reverse("income_statement", args=[self.person.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_period_scoping(self):
        resp = self.client.get(
            reverse("income_statement", args=[self.project.pk]),
            {"period": self.project_period.pk},
        )
        self.assertEqual(resp.status_code, 200)

    def test_invalid_period_returns_404(self):
        resp = self.client.get(
            reverse("income_statement", args=[self.project.pk]), {"period": 999999}
        )
        self.assertEqual(resp.status_code, 404)


class BalanceSheetViewTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)
        self._tx(self.person, self.project, TransactionType.PROJECT_FUNDING_PAYMENT, "1000.00")
        self._tx(self.client_entity, self.project, TransactionType.SALE_ISSUANCE, "200.00")

    def test_renders_and_reconciles(self):
        resp = self.client.get(reverse("balance_sheet", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)
        stmt = resp.context["statement"]
        self.assertEqual(stmt["equity"], stmt["assets"] - stmt["liabilities"])
        self.assertContains(resp, "Total Assets = Total Liabilities + Total Equity")

    def test_drill_down_links(self):
        resp = self.client.get(reverse("balance_sheet", args=[self.project.pk]))
        self.assertContains(resp, reverse("entity_payables_list", args=[self.project.pk]))
        self.assertContains(resp, reverse("entity_receivables_list", args=[self.project.pk]))
        self.assertContains(resp, reverse("entity_payment_transactions_list", args=[self.project.pk]))
        self.assertContains(resp, reverse("stock_detail", args=[self.project.pk]))


class CashFlowViewTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)
        self._tx(self.person, self.project, TransactionType.PROJECT_FUNDING_PAYMENT, "1000.00")
        self._tx(self.project, self.vendor, TransactionType.PURCHASE_PAYMENT, "300.00")

    def test_cash_flow_renders(self):
        resp = self.client.get(reverse("cash_flow", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["statement"]["closing"], Decimal("700.00"))
        self.assertContains(resp, "Ending cash")

    def test_person_cash_flow_renders(self):
        resp = self.client.get(reverse("cash_flow", args=[self.person.pk]))
        self.assertEqual(resp.status_code, 200)


class EquityStatementViewTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)
        self._tx(self.world, self.person, TransactionType.CASH_INJECTION_PAYMENT, "500.00")

    def test_person_equity_renders(self):
        resp = self.client.get(reverse("equity_statement", args=[self.person.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["statement"]["closing"], Decimal("500.00"))
        self.assertContains(resp, "Equity at end of period")

    def test_project_equity_renders(self):
        resp = self.client.get(reverse("equity_statement", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)


class PaymentTransactionsTypeFilterTest(ReportBaseTestCase):
    def setUp(self):
        self.client.force_login(self.officer)
        self._tx(self.project, self.vendor, TransactionType.PURCHASE_PAYMENT, "50.00")
        self._tx(self.project, self.world, TransactionType.EXPENSE_PAYMENT, "30.00")

    def test_type_filter_limits_rows(self):
        resp = self.client.get(
            reverse("entity_payment_transactions_list", args=[self.project.pk]),
            {"type": TransactionType.PURCHASE_PAYMENT},
        )
        self.assertEqual(resp.status_code, 200)
        txs = resp.context["transactions"]
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].type, TransactionType.PURCHASE_PAYMENT)
