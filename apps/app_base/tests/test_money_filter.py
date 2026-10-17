"""Tests for the reusable money-display template filters."""

from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from apps.app_base.templatetags.money import money, money_plain, money_signed


class MoneyFilterTests(SimpleTestCase):
    def test_decimal_is_grouped_and_padded(self):
        self.assertEqual(money(Decimal("1234567.5")), "$1,234,567.50")

    def test_integer_is_padded(self):
        self.assertEqual(money(1234), "$1,234.00")

    def test_float_is_padded(self):
        self.assertEqual(money(1234.5), "$1,234.50")

    def test_numeric_string_is_supported(self):
        self.assertEqual(money("1234.5"), "$1,234.50")

    def test_negative_uses_leading_minus(self):
        self.assertEqual(money(Decimal("-1234.56")), "-$1,234.56")

    def test_none_renders_zero(self):
        self.assertEqual(money(None), "$0.00")

    def test_blank_string_renders_zero(self):
        self.assertEqual(money(""), "$0.00")

    def test_invalid_value_renders_zero(self):
        self.assertEqual(money("not-a-number"), "$0.00")

    def test_non_finite_value_renders_zero(self):
        self.assertEqual(money(Decimal("NaN")), "$0.00")
        self.assertEqual(money(Decimal("Infinity")), "$0.00")

    def test_more_than_two_decimals_are_rounded(self):
        self.assertEqual(money(Decimal("1.005")), "$1.01")

    def test_symbol_override(self):
        self.assertEqual(money(Decimal("10"), "€"), "€10.00")

    @override_settings(CURRENCY_SYMBOL="£")
    def test_symbol_from_settings(self):
        self.assertEqual(money(Decimal("10")), "£10.00")

    @override_settings(CURRENCY_SYMBOL="")
    def test_empty_setting_symbol_falls_back_to_default(self):
        self.assertEqual(money(Decimal("10")), "$10.00")

    def test_empty_symbol_argument_falls_back_to_default(self):
        self.assertEqual(money(Decimal("10"), ""), "$10.00")

    def test_money_plain_has_no_symbol(self):
        self.assertEqual(money_plain(Decimal("1234.5")), "1,234.50")

    def test_money_plain_negative(self):
        self.assertEqual(money_plain(Decimal("-1234.5")), "-1,234.50")

    def test_money_signed_positive(self):
        self.assertEqual(money_signed(Decimal("5")), "+$5.00")

    def test_money_signed_negative(self):
        self.assertEqual(money_signed(Decimal("-5")), "-$5.00")

    def test_money_signed_zero(self):
        self.assertEqual(money_signed(0), "+$0.00")

    def test_money_signed_symbol_override(self):
        self.assertEqual(money_signed(Decimal("5"), "€"), "+€5.00")


class MoneyFilterTemplateTests(SimpleTestCase):
    def render(self, source):
        return Template("{% load money %}" + source).render(Context({}))

    def test_money_tag(self):
        self.assertEqual(self.render("{{ 1234.5|money }}"), "$1,234.50")

    def test_money_plain_tag(self):
        self.assertEqual(self.render("{{ 1234.5|money_plain }}"), "1,234.50")

    def test_money_signed_tag(self):
        self.assertEqual(self.render("{{ -1234.5|money_signed }}"), "-$1,234.50")

    def test_money_tag_with_symbol_argument(self):
        self.assertEqual(self.render('{{ 1234.5|money:"€" }}'), "€1,234.50")

    def test_money_tag_with_variable_symbol(self):
        out = Template("{% load money %}{{ v|money:sym }}").render(
            Context({"v": Decimal("10"), "sym": "€"})
        )
        self.assertEqual(out, "€10.00")
