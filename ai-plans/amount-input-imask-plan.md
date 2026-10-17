# Amount input rebuild on IMask

## Problem

The custom `AmountInputFormatter` re-derived the entire string on every keystroke
(`toFixed(2)` + `toLocaleString('en-US')` + manual comma counting). Consequences:

- The caret jumped unexpectedly while typing.
- The decimal part could not be edited continuously (cursor returned to the
  integer part after reaching the decimal point).
- Poor integration with the Arabic (RTL) layout.

Requirements: use a ready-made, well-tested library, add thousands separators
(grouping by three), and use larger fonts.

## Decision

Adopt **IMask** (`mask: Number`) — a standalone, no-build dependency with a
model/view split that tracks the caret by digit. Vendored locally as
`static/js/vendor/imask.min.js` (7.6.1, MIT). RTL is handled by forcing the numeric
field to `direction: ltr` (numbers are LTR even in Arabic UI). Western digits
`0-9`, `,` thousands separator, `.` decimal.

Kept the existing visible-input + hidden-name-twin architecture (server receives a
clean decimal), plus the `+`/`−` steppers and Arrow Up/Down stepping.

## Implementation

- `static/js/vendor/imask.min.js`, `imask.LICENSE.txt`, `README.txt` — vendored.
- `static/js/amount-input.js` — replaced `amount-input-formatter.js`.
  - Converts each `input.amount-input` to `type="text"`, strips `name` to
    `data-original-name`, adds `dir="ltr"`, creates the hidden twin.
  - IMask config: `scale: 2`, `thousandsSeparator: ','`, `radix: '.'`,
    `padFractionalZeros` toggled false on focus / true on blur (continuous decimal
    editing + 2-decimal resting display), `normalizeZeros: true`, `signed: false`.
  - `accept` handler syncs the hidden twin and fires bubbling `input`/`change`.
  - A `WeakMap` is the source of truth for initialised state, so formset-cloned
    rows (which keep DOM attributes but lose listeners) re-initialise cleanly;
    existing hidden twins/buttons are reused, not duplicated.
  - `window.AmountInput` API: `getValue`, `getNumber`, `setValue`, `getInstance`.
- `templates/base.html` — load IMask then `amount-input.js`.
- `static/js/operation-formset.js`, `static/js/partial-payment-subform.js` — use the
  helpers (also fixes `parseFloat("1,234.50") === 1` style bugs).
- `add_payment_form.html`, `evaluation_form.html` — inline scripts use the helpers;
  evaluation's pre-selected product init moved into `DOMContentLoaded`.
- `static/css/main.css` — `--amount-font-size: 1.4rem`, `font-variant-numeric:
  tabular-nums`, `direction: ltr`, logical-property button radii; `.amount-total`
  and `$` label bumped to match.
- `ui_tests/base.py::fill_amount` — drives `AmountInput.setValue`.

## Verification

- `manage.py check` clean.
- `node --check` clean on the three JS files.
- Unit-checked IMask `MaskedNumber` behaviour in Node (padding, separators,
  empty value).
- `apps.app_operation.tests.views.test_evaluation_ownership` and
  `apps.app_adjustment.tests.test_adjustment_adjustment_validation` pass.

## Notes / follow-ups

- Focusing a field briefly drops a trailing `.00` (IMask re-renders with
  `padFractionalZeros:false`); it is restored on blur. Acceptable trade-off for
  free decimal editing.
- UI (Selenium) suite is serial-only; not run here. `fill_amount` was updated.
