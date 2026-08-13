# Plan: Remove Profit Distribution & Loss Coverage Operations

## Goal

Remove the **Profit Distribution** (Op 9) and **Loss Coverage** (Op 10) operations from the
system. Projects keep computing P&L, but moving money between project and shareholder funds
is done through the existing operations (Project Funding / Project Refund / Internal
Transfer / Cash Injection / Cash Withdrawal).

**Decision (confirmed with user):** Full code removal; **keep historical rows** (no data
purge — the DB is developmental per `remove-batch-tracking-plan.md` precedent, so only schema
migrations are produced). Also remove the now-orphaned `Operation.plan` field and the
`ShareholderAllocation` model, which exist only for these two operations.

## Why P&L is unaffected

[`Entity.profit_loss()`](apps/app_entity/models/__init__.py:546) is driven entirely by
SALE / PURCHASE / EXPENSE / CAPITAL_GAIN / CAPITAL_LOSS / CORRECTION / CONSUMPTION
*issuance* transactions. `PROFIT_DISTRIBUTION_*` and `LOSS_COVERAGE_*` transaction types are
**not** part of the income/cost sets, so removing them does not change the P&L result.

## Changes

### Models (app_operation)
- Delete proxy models: `op_profit_distribution.py`, `op_loss_coverage.py`.
- Deregister in `models/proxies/__init__.py` (imports, `PROXY_MAP`, `__all__`).
- Deregister in `models/__init__.py` (imports, `__all__`).
- Remove `PROFIT_DISTRIBUTION` / `LOSS_COVERAGE` from `OperationType` choices.
- Remove the `plan` FK field on `Operation` (was used only by the two operations).
- Remove `FinancialPeriod.distributed` / `covered` / `remaining_distributable` /
  `remaining_coverable` and `allocations_balanced` (keep `amount` / `is_profit` / `is_loss`).
- Delete `models/share_allocation.py` (`ShareholderAllocation`).
- Admin: drop `plan` from the `OperationAdmin` fieldset.

### Transactions (app_transaction) + Entity
- Remove `LOSS_COVERAGE_ISSUANCE/PAYMENT` and `PROFIT_DISTRIBUTION_ISSUANCE/PAYMENT`
  transaction types and all their registrations (`payment_types()`, `issuance_types()`,
  `_TX_ENTITY_TYPE_MAP`, `_TX_OPERATION_MAP`).
- Remove `PROFIT_DISTRIBUTION_*` references from `Entity.payables_at()` / `receivables_at()`
  and the transaction payables/receivables view lists.

### UI (templates)
- Remove the **Loss Coverage** dropdown item in `operation_list.html`.
- Remove the **Profit Distribution / Loss Coverage** summary cards in `period_detail.html`
  (keep the Profit/Loss amount display).

### Tests
- Delete `tests/operations/distribution/` (all files).
- Delete `tests/period/test_distribution_plan_period_profit_loss_properties.py`.
- Remove the `PROFIT_DISTRIBUTION` / `LOSS_COVERAGE` rows from the `COVERAGE_MANIFEST` in
  `tests/base.py`.

### Migrations (schema-only, no data purge)
- `app_operation`: `RemoveField(plan)`, `AlterField(operation_type choices)`,
  `DeleteModel(ProfitDistributionOperation)`, `DeleteModel(LossCoverageOperation)`,
  `DeleteModel(ShareholderAllocation)`.
- `app_transaction`: `AlterField(type choices)` removing the 4 transaction types.

### Specs / docs / locale
- Delete `specs/operations/op_9_profit_distribution.md` and `op_10_loss_coverage.md`.
- Remove Op 9/10 from `specs/operations/README.md`, `specs/operations/operations-comparison.md`,
  `specs/README.md`.
- Remove the Profit Distribution / Loss Coverage line from
  `docs/guides/PERIOD_FEATURE_SUMMARY.md`.
- Remove the Op 9/10 rows and review notes from `Review.md`.
- Remove the "Loss Coverage" msgid from `locale/ar/LC_MESSAGES/django.po`.

### Verification
- `python manage.py check`
- Full suite with `python3 manage.py test --parallel=10 --create-db` (schema changed), capture
  output to a temp file, inspect errors, then `--reuse-db`; delete the temp file.
- Append outcomes to this file and create a git commit.

## Files touched

- `apps/app_operation/models/proxies/op_profit_distribution.py` (delete)
- `apps/app_operation/models/proxies/op_loss_coverage.py` (delete)
- `apps/app_operation/models/proxies/__init__.py`
- `apps/app_operation/models/__init__.py`
- `apps/app_operation/models/operation_type.py`
- `apps/app_operation/models/operation.py`
- `apps/app_operation/models/period.py`
- `apps/app_operation/models/share_allocation.py` (delete)
- `apps/app_operation/admin.py`
- `apps/app_operation/templates/app_operation/operation_list.html`
- `apps/app_operation/templates/app_operation/period_detail.html`
- `apps/app_operation/tests/base.py`
- `apps/app_operation/tests/operations/distribution/` (delete)
- `apps/app_operation/tests/period/test_distribution_plan_period_profit_loss_properties.py` (delete)
- `apps/app_transaction/transaction_type.py`
- `apps/app_transaction/views.py`
- `apps/app_entity/models/__init__.py`
- `specs/operations/op_9_profit_distribution.md` (delete)
- `specs/operations/op_10_loss_coverage.md` (delete)
- `specs/operations/README.md`
- `specs/operations/operations-comparison.md`
- `specs/README.md`
- `docs/guides/PERIOD_FEATURE_SUMMARY.md`
- `Review.md`
- `locale/ar/LC_MESSAGES/django.po`

## Implementation outcome (executed)

- **Models** — Deleted `op_profit_distribution.py` / `op_loss_coverage.py` / `share_allocation.py`;
  deregistered the two proxies from `models/proxies/__init__.py` and `models/__init__.py`;
  removed `PROFIT_DISTRIBUTION` / `LOSS_COVERAGE` from `OperationType`; removed the `plan` FK
  on `Operation`; removed `FinancialPeriod.distributed / covered / remaining_distributable /
  remaining_coverable / allocations_balanced`; dropped `plan` from `OperationAdmin`.
- **Transactions/Entity** — Removed the four `PROFIT_DISTRIBUTION_*` / `LOSS_COVERAGE_*`
  transaction types and all registrations (`payment_types()`, `issuance_types()`,
  `_TX_ENTITY_TYPE_MAP`, `_TX_OPERATION_MAP`); removed the `PROFIT_DISTRIBUTION_*` references
  from `Entity.payables_at()` / `receivables_at()` and the transaction payables/receivables view.
- **UI** — Removed the Loss Coverage dropdown item from `operation_list.html` and the
  Profit Distribution / Loss Coverage cards from `period_detail.html` (kept the Profit/Loss
  amount display — P&L is still computed by `Entity.profit_loss()`).
- **Tests** — Deleted `tests/operations/distribution/` and
  `tests/period/test_distribution_plan_period_profit_loss_properties.py`; removed the
  PROFIT_DISTRIBUTION / LOSS_COVERAGE rows from the `COVERAGE_MANIFEST` in `tests/base.py`.
- **Migrations** — `app_operation/0009_...` (RemoveConstraint + DeleteModel ×3 + RemoveField
  `plan` + AlterField `operation_type` choices) and `app_transaction/0002_alter_transaction_type.py`
  (AlterField `type` choices). Schema-only — historical Operation/Transaction rows are kept
  (no data purge). Note: removing the `plan` column and the `ShareholderAllocation` table is
  inherent to removing those models.
- **Specs/docs/locale** — Deleted `op_9_profit_distribution.md` / `op_10_loss_coverage.md`;
  removed Op 9/10 from `specs/operations/README.md`, `specs/operations/operations-comparison.md`,
  `specs/README.md`, `docs/guides/PERIOD_FEATURE_SUMMARY.md`, and the two `ai-plans` docs
  (`improve-operation-test-suite-plan.md`, `manual-test-plan.md`); removed the "Loss Coverage"
  msgid from `locale/ar/LC_MESSAGES/django.po`.
- **Verification** — `manage.py check` clean; `makemigrations --check --dry-run` → no changes;
  full suite `manage.py test --parallel=10` (fresh DB) → **1325 tests, OK**.
