# Operation Detail Page — Navigation & Settlement UX Improvement

## Goal
Improve the operation detail page ([`operation_detail.html`](../apps/app_operation/templates/app_operation/operation_detail.html)) so it:

1. Provides **operations-list links for both counterpart entities** (source and
   destination) in the navigation bar, exempting virtual (system/world) entities.
   The previous parent "Operations" breadcrumb was broken because the navigation map
   tried to map `source_pk` from a URL that only carries `pk`.
2. **Hides the "Record Repayment" action** once an operation is fully repaid, so a
   user is never offered an action that would only fail validation.
3. **Hides the "Record Payment" action** once an operation is fully settled, matching
   the repayment behaviour above.
4. Shows the repayment progress (Repaid / Remaining) in the page header for
   `has_repayment` operations (Loan, Worker Advance), matching the existing
   Paid / Outstanding display used by `is_partially_payable` operations.

## Data model notes
- `Operation.period_entity` returns the URL-role entity based on `_source_role` /
  `_dest_role` set on each proxy.
- `Operation.is_fully_repayed`, `amount_repayed`, `amount_remaining_to_repay` come
  from the repayment mixins in `apps/app_base/mixins.py`.
- `Operation.is_fully_settled`, `amount_settled`, `amount_remaining_to_settle` come
  from the payment mixins in `apps/app_base/mixins.py`.
- The operations list URL pattern is `operation_list_view` with kwarg `person_pk`.
- Virtual entities (entity_type `system` / `world`) have no detail page and no
  meaningful operations list, so they are exempt from both nav links.

## Changes
### 1. Navigation context — `apps/app_base/context_processors.py`
- Views may now append extra related views to the navigation bar via a new
  `add_related` list inside `request.navigation_overrides`; each entry is a
  `{title, url}` dict.

### 2. View — `apps/app_operation/views/detail.py`
- Build an `add_related` list containing an operations-list link for each real
  (non-virtual) counterpart entity, labelled `Operations: <entity name>` and pointing
  to `operation_list_view` with `person_pk=<entity.pk>`.
- Merge `related_urls` and `add_related` into `request.navigation_overrides`.

### 3. Template — `apps/app_operation/templates/app_operation/snippets/address_bar.html`
- Add a repayment status line for `has_repayment` operations: `Repaid: <amt>` and
  `Remaining: <amt>` (color-coded by `is_fully_repayed`), mirroring the existing
  Paid / Outstanding line for `is_partially_payable` operations.
- (The temporary page-level "Operations" breadcrumb added earlier was removed in
  favour of the navigation-bar links.)

### 4. Templates — settlement action buttons
- `financial_summary.html`: the header **Record Payment** button is now guarded by
  `and not operation.is_fully_settled`.
- `invoice_repayment_summary.html`: the header **Record Repayment** button is now
  guarded by `{% if not operation.is_fully_repayed %}`.

## Verification
- `python manage.py check`
- `python manage.py test apps.app_operation.tests.views.test_views_get_operation_detail_view --parallel=8`
- `python manage.py test apps.app_operation.tests.views apps.app_base --parallel=8`

## Implementation notes (executed)
- [`apps/app_base/context_processors.py`](../apps/app_base/context_processors.py):
  - Processed `overrides.get('add_related', [])` and appended the entries to
    `nav_context['related_views']`.
- [`apps/app_operation/views/detail.py`](../apps/app_operation/views/detail.py):
  - Added `add_related` with one `Operations: <name>` link per non-virtual source and
    destination; merged with the existing `related_urls` overrides.
- [`apps/app_operation/templates/app_operation/snippets/address_bar.html`](../apps/app_operation/templates/app_operation/snippets/address_bar.html):
  - Kept the `Repaid:` / `Remaining:` line for `operation.has_repayment` operations;
    removed the earlier breadcrumb "Operations" link.
- [`apps/app_operation/templates/app_operation/snippets/detail/financial_summary.html`](../apps/app_operation/templates/app_operation/snippets/detail/financial_summary.html):
  - Header "Record Payment" button hidden when `operation.is_fully_settled`.
- [`apps/app_operation/templates/app_operation/snippets/detail/invoice_repayment_summary.html`](../apps/app_operation/templates/app_operation/snippets/detail/invoice_repayment_summary.html):
  - Header "Record Repayment" button hidden when `operation.is_fully_repayed`.
- [`apps/app_operation/tests/views/test_views_get_operation_detail_view.py`](../apps/app_operation/tests/views/test_views_get_operation_detail_view.py):
  - `test_operation_detail_shows_both_sides_operations_list_links` — both real
    counterparts (project + vendor) get operations-list links.
  - `test_operation_detail_exempts_virtual_entity_operations_link` — the world
    counterpart gets no operations-list link.
  - `test_operation_detail_hides_record_payment_when_fully_settled` /
    `test_operation_detail_shows_record_payment_when_not_fully_settled`.
  - `test_operation_detail_hides_record_repayment_when_fully_repayed` /
    `test_operation_detail_shows_record_repayment_when_not_fully_repayed`.
  - Stored the singleton world entity as `self.world` in `setUp`; funds projects via
    `CapitalGainOperation` (CashInjection targets Person only).

## Test results
- `manage.py check` — no issues.
- `manage.py test apps.app_operation.tests.views.test_views_get_operation_detail_view --parallel=8` — 11 passed.
- `manage.py test apps.app_operation.tests.views apps.app_base --parallel=8` — 77 passed.
