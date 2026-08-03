"""
Unit tests for ``OperationDataValidator`` and ``ParsedOperationData``.

Tests are organised by parser method, plus an integration test for the
public ``validate()`` method.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.app_operation.validators import OperationDataValidator, ParsedOperationData

# =========================================================================
# ParsedOperationData
# =========================================================================


class ParsedOperationDataTest(SimpleTestCase):
    def test_defaults(self):
        """Default values are set correctly."""
        data = ParsedOperationData(
            date=date(2024, 6, 1),
            description="Test operation",
        )
        self.assertIsNone(data.selected_category_id)
        self.assertEqual(data.amount_paid, Decimal("0.00"))
        self.assertIsNone(data.raw_post)
        self.assertEqual(data.errors, [])

    def test_all_fields(self):
        """All fields can be set explicitly."""
        raw = {"key": "value"}
        data = ParsedOperationData(
            date=date(2024, 6, 15),
            description="Full data",
            selected_category_id=3,
            amount_paid=Decimal("500.00"),
            raw_post=raw,
            errors=["something"],
        )
        self.assertEqual(data.selected_category_id, 3)
        self.assertEqual(data.amount_paid, Decimal("500.00"))
        self.assertIs(data.raw_post, raw)
        self.assertEqual(data.errors, ["something"])


# =========================================================================
# OperationDataValidator — _parse_date
# =========================================================================


class ParseDateTest(SimpleTestCase):
    def test_valid_date_string(self):
        v = OperationDataValidator({"date": "2024-06-15"}, {})
        errors: list[str] = []
        result = v._parse_date(errors)
        self.assertEqual(result, date(2024, 6, 15))
        self.assertEqual(errors, [])

    def test_empty_date_returns_today(self):
        v = OperationDataValidator({"date": ""}, {})
        errors: list[str] = []
        result = v._parse_date(errors)
        self.assertEqual(result, date.today())
        self.assertEqual(errors, [])

    def test_missing_date_returns_today(self):
        v = OperationDataValidator({}, {})
        errors: list[str] = []
        result = v._parse_date(errors)
        self.assertEqual(result, date.today())
        self.assertEqual(errors, [])

    def test_invalid_date_appends_error_and_returns_today(self):
        v = OperationDataValidator({"date": "not-a-date"}, {})
        errors: list[str] = []
        result = v._parse_date(errors)
        self.assertEqual(result, date.today())
        self.assertEqual(errors, ["Invalid date format."])


# =========================================================================
# OperationDataValidator — _parse_category
# =========================================================================


class ParseCategoryTest(SimpleTestCase):
    def test_valid_category_id(self):
        v = OperationDataValidator({"category": "42"}, {})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertEqual(result, 42)
        self.assertEqual(errors, [])

    def test_empty_category_returns_none(self):
        v = OperationDataValidator({"category": ""}, {})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertIsNone(result)
        self.assertEqual(errors, [])

    def test_missing_category_returns_none(self):
        v = OperationDataValidator({}, {})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertIsNone(result)
        self.assertEqual(errors, [])

    def test_missing_required_category_appends_error(self):
        v = OperationDataValidator({}, {"category_required": True})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertIsNone(result)
        self.assertEqual(errors, ["Category is required for this operation."])

    def test_invalid_category_string_appends_error(self):
        v = OperationDataValidator({"category": "abc"}, {})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertIsNone(result)
        self.assertEqual(errors, ["Invalid category selection."])

    def test_non_integer_numeric_string_appends_error(self):
        v = OperationDataValidator({"category": "12.5"}, {})
        errors: list[str] = []
        result = v._parse_category(errors)
        self.assertIsNone(result)
        self.assertEqual(errors, ["Invalid category selection."])


# =========================================================================
# OperationDataValidator — _parse_amount_paid
# =========================================================================


class ParseAmountPaidTest(SimpleTestCase):
    def test_valid_amount(self):
        v = OperationDataValidator({"amount_paid": "150.75"}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("150.75"))
        self.assertEqual(errors, [])

    def test_zero_amount(self):
        v = OperationDataValidator({"amount_paid": "0.00"}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("0.00"))
        self.assertEqual(errors, [])

    def test_empty_amount_returns_zero(self):
        v = OperationDataValidator({"amount_paid": ""}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("0.00"))
        self.assertEqual(errors, [])

    def test_missing_amount_returns_zero(self):
        v = OperationDataValidator({}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("0.00"))
        self.assertEqual(errors, [])

    def test_negative_amount_appends_error(self):
        v = OperationDataValidator({"amount_paid": "-10.00"}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("0.00"))
        self.assertEqual(errors, ["Amount paid cannot be negative."])

    def test_invalid_amount_appends_error(self):
        v = OperationDataValidator({"amount_paid": "not-money"}, {})
        errors: list[str] = []
        result = v._parse_amount_paid(errors)
        self.assertEqual(result, Decimal("0.00"))
        self.assertEqual(errors, ["Invalid amount paid value."])


# =========================================================================
# OperationDataValidator — validate (integration)
# =========================================================================


class ValidateIntegrationTest(SimpleTestCase):
    def test_valid_data_returns_parsed_operation_data(self):
        post = {
            "date": "2024-07-01",
            "description": "Integration test",
            "category": "5",
            "amount_paid": "200.00",
        }
        v = OperationDataValidator(post, {"category_required": True})
        result = v.validate()

        self.assertIsInstance(result, ParsedOperationData)
        self.assertEqual(result.date, date(2024, 7, 1))
        self.assertEqual(result.description, "Integration test")
        self.assertEqual(result.selected_category_id, 5)
        self.assertEqual(result.amount_paid, Decimal("200.00"))
        self.assertIs(result.raw_post, post)

    def test_minimal_valid_data(self):
        """Only date and description are truly required; everything else has defaults."""
        post = {"date": "2024-07-01", "description": "Minimal"}
        v = OperationDataValidator(post, {})
        result = v.validate()

        self.assertEqual(result.date, date(2024, 7, 1))
        self.assertEqual(result.description, "Minimal")
        self.assertIsNone(result.selected_category_id)
        self.assertEqual(result.amount_paid, Decimal("0.00"))

    def test_validation_error_on_invalid_date(self):
        v = OperationDataValidator({"date": "bad-date", "description": "x"}, {})
        with self.assertRaises(ValidationError) as ctx:
            v.validate()
        self.assertIn("Invalid date format.", str(ctx.exception))

    def test_validation_error_on_negative_amount(self):
        v = OperationDataValidator(
            {"date": "2024-07-01", "description": "x", "amount_paid": "-5"},
            {},
        )
        with self.assertRaises(ValidationError) as ctx:
            v.validate()
        self.assertIn("Amount paid cannot be negative.", str(ctx.exception))

    def test_validation_error_on_required_category(self):
        v = OperationDataValidator(
            {"date": "2024-07-01", "description": "x"},
            {"category_required": True},
        )
        with self.assertRaises(ValidationError) as ctx:
            v.validate()
        self.assertIn("Category is required for this operation.", str(ctx.exception))

    def test_multiple_errors_aggregated(self):
        """All errors are collected and joined before raising."""
        v = OperationDataValidator(
            {"date": "bad", "description": "x", "amount_paid": "neg"},
            {"category_required": True},
        )
        with self.assertRaises(ValidationError) as ctx:
            v.validate()
        msg = str(ctx.exception)
        self.assertIn("Invalid date format.", msg)
        self.assertIn("Category is required for this operation.", msg)
        # amount_paid will raise ValueError which is caught -> "Invalid amount paid value."
        self.assertIn("Invalid amount paid value.", msg)
