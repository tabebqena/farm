# Unified money display

## Problem

Read-only monetary amounts were formatted ad-hoc: 118 `floatformat:2` uses
(no grouping), raw `Decimal.__str__` behind `{{ currency }}`, hardcoded `$`, and
hand-built `"$ " + x.toFixed(2)` strings in JS. Reports had no currency symbol.
`entity_detail.html` referenced a non-existent `entity.currency`.

## Decisions

- Western digits, `,` grouping, `.` decimal, `$` prefix (single-currency system),
  matching the IMask amount inputs in both EN and AR.
- Negatives use a leading minus (`-$1,234.56`); `None`/blank/invalid → `$0.00`.
- Tabular figures (no monospace) for report/ledger tables.
- Migrate all templates in one pass; leave quantities/counts on `floatformat`.

## Implementation

- `apps/app_base/templatetags/money.py` — `money`, `money_plain`, `money_signed`.
  Coerces Decimal/int/float/str, half-up rounds to 2 dp, groups thousands, prefix
  symbol from `settings.CURRENCY_SYMBOL` or an override arg.
- `apps/app_base/context_processors.py` — `currency()`; registered in
  `TEMPLATES["OPTIONS"]["context_processors"]`.
- `static/js/money.js` — `window.FarmMoney.{format,signed,plain}` via
  `Intl.NumberFormat('en-US', …)`; symbol from `<body data-currency>`.
- `templates/base.html` — `data-currency="{{ currency }}"` and loads `money.js`.
- `static/css/main.css` — `.money` utility.
- Migrated 40 templates across `app_report`, `app_entity`, `app_operation`,
  `app_adjustment`, `app_transaction` to `|money`; blocktrans money strings were
  wrapped with `{% with x=value|money %}` (filters are not allowed inside
  blocktrans).
- JS totals migrated to `FarmMoney`.
- `apps/app_base/tests/test_money_filter.py` — 25 tests, full coverage of the
  filter module (valid values, None/blank/invalid/NaN/Infinity, rounding,
  symbol override, settings symbol, all three filters, template usage).

## Verification

- `manage.py check` clean; all 41 changed templates compile.
- `apps.app_base.tests.test_money_filter` — 25 pass.
- Operation/entity/adjustment view tests (detail, list, period, payment,
  repayment, effective amount) — 48 pass.
- `node --check` clean on all changed JS.

## Notes / follow-ups

- Views still inject `currency` in ~12 places; now redundant given the context
  processor but harmless. Can be removed later.
- Quantity displays (`stock_history`, `stock_detail`) intentionally unchanged.

## Follow-up: Egyptian pound default

- `settings.CURRENCY_SYMBOL` → `"E£"`; `DEFAULT_SYMBOL` in `money.py` and the
  `FarmMoney` JS fallback follow suit.
- Replaced remaining hardcoded `$` input-group prefixes and `$0.00` seed values
  in templates with `{{ currency }}` (adjustment forms, operation amount groups,
  wizard steps, category relation form, invoice formset grand total, partial
  payment subform).
- Updated filter tests to expect `E£`; the two operation view tests that
  asserted `currency == "$"` now compare against `settings.CURRENCY_SYMBOL`, and
  fund-display assertions expect the grouped/symbol form (`E£1,000.00`).
