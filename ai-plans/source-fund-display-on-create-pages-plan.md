# Plan: Display Current Fund of the Source Entity on Create Pages

## Goal
For every operation create page and transaction (payment / repayment) create page,
show the current fund balance of the source entity (the entity whose fund is debited),
so the user can see how much money is available before recording an entry.

## Decisions
- "Source entity" is resolved from the operation config (`_source_role` / `_dest_role`):
  - source role `url` → the project the page was opened from (source balance = project balance).
  - source role `post` (e.g. Sale's client, Project Refund's funder) → the source is only
    known once chosen; the create page falls back to the URL/primary entity's fund until then.
  - source role `system`/`world` → falls back to the URL/primary entity's fund.
- Currency comes from `settings.CURRENCY_SYMBOL`.
- A single reusable snippet renders the balance so all pages stay consistent.

## Implemented

### Reusable snippet
- `apps/app_operation/templates/app_operation/snippets/create-form/fund-balance.html`
  - Renders a "Current Fund" alert with the entity name and `fund_entity.balance`
    (options: `fund_entity`, `fund_label`, `fund_currency`, `fund_color`).
  - Labels ("Source Fund", "Paying Fund", "Repaying Fund") are passed via
    `{% trans '...' as var %}` so they participate in localization.

### Operation create pages
- `apps/app_operation/views/create_operation/base.py`
  - `OperationCreateView._build_context` now adds `source_entity`
    (`source_entity or url_entity`), `source_balance` (`source_entity.balance`), and `currency`.
  - This covers every `operation_create_view` type, plus Birth / Death / Sale forms
    (which extend the generic form).
- `apps/app_operation/templates/app_operation/generic_form.html`
  - Includes the fund-balance snippet below the primary entity alert.
- `apps/app_operation/views/create_operation/create_sale_view.py`
  - Removed the now-redundant `project_balance` override (generic form covers it via fallback).
- `apps/app_operation/views/create_operation/evaluation.py`
  - `_build_evaluation_context` adds `source_entity`, `source_balance`, `currency`.
- `apps/app_operation/templates/app_operation/evaluation_form.html`
  - Includes the fund-balance snippet.
- `apps/app_operation/templates/app_operation/purchase_wizard.html` and `sale_wizard.html`
  - Include the snippet with `fund_entity=project` on every wizard step.
- `apps/app_operation/templates/app_operation/purchase_invoice.html` and `sale_invoice.html`
  - Include the snippet below the page heading.

### Transaction (payment / repayment) create pages
- `apps/app_operation/views/record_transaction.py`
  - `record_transaction_payment` adds `source_entity` = `operation.payment_source_fund`,
    `source_balance`, `currency`.
  - `record_transaction_repayment` adds `source_entity` = `operation.payment_target_fund`
    (the entity that repays), `source_balance`, `currency`.
- `apps/app_operation/templates/app_operation/add_payment_form.html` and
  `add_repayment_form.html` include the snippet.

### Bug fix (supporting)
- `apps/app_inventory/forms.py` — `HasTagSelect.create_option` did not accept the
  `subindex` keyword that current Django passes, causing `TypeError` when rendering any
  invoice-based create page (Purchase/Sale). Updated the signature to accept and forward
  `subindex` (dropped the obsolete `subgroup` param).

## Tests
- `apps/app_operation/tests/views/test_views_get_operation_create_view.py` (new):
  - purchase / expense / worker-advance create → `source_entity` == project,
    `source_balance` == `project.balance`, `currency` == `$`
  - purchase create renders "Source Fund", project name, and the balance value
  - sale create on GET falls back to the project fund
  - payment create exposes the project (payment source) fund and renders "Paying Fund"
  - repayment create exposes the debtor (payment target) fund and renders "Repaying Fund"
- `apps/app_operation/tests/views/test_views_get_purchase_wizard_view.py` and
  `test_views_get_sale_wizard_view.py`: wizard renders "Source Fund" + project name.

## Verification
- `manage.py check` -> no issues
- `manage.py test apps.app_operation.tests.views --parallel=8` -> 44 passed
- `manage.py test apps.app_operation --parallel=8` -> 932 passed
- `manage.py test apps.app_inventory --parallel=8` -> 128 passed
