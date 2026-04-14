# Profit Distribution & Loss Coverage

**Epic:** 9.3 — Project Capital Operations
**Spec type:** Feature (two linked operation types + supporting model)

---

## Process Overview

At the end of each financial period, a project's P&L is crystallised into a **DistributionPlan**.
The plan drives two operation types depending on the sign of the net result:

```
Period closes
      │
      ▼
DistributionPlan.calculate_amount(entity, period)
      │
      ├─ amount > 0  (profit) ──► ProfitDistributionOperation(s)
      │                              project.fund → shareholder.fund
      │                              capped at plan.remaining_distributable
      │
      ├─ amount < 0  (loss)   ──► LossCoverageOperation(s)
      │                              shareholder.fund → project.fund
      │                              capped at plan.remaining_coverable
      │
      └─ amount == 0 (break-even) ──► no operations allowed
```

### ShareholderAllocation (advisory)

Before distributing/covering, the officer may record the intended split
across shareholders as percentages. These are **instructional only** — the
system does not enforce them, but `plan.allocations_balanced` checks whether
they sum to 100 %.

---

## Models

### DistributionPlan

| Field    | Type          | Notes                              |
|----------|---------------|------------------------------------|
| entity   | FK → Entity   | must be a Project entity; immutable |
| period   | FK → FinancialPeriod | must belong to `entity`; must be closed; immutable |
| amount   | DecimalField  | P&L snapshot; immutable; positive = profit, negative = loss |

**Unique constraint:** one plan per `(entity, period)`.

**Computed properties:**

| Property                  | Returns                                         |
|---------------------------|-------------------------------------------------|
| `is_profit`               | `amount > 0`                                    |
| `is_loss`                 | `amount < 0`                                    |
| `distributed`             | sum of active ProfitDistribution ops on this plan |
| `covered`                 | sum of active LossCoverage ops on this plan     |
| `remaining_distributable` | `amount − distributed` (0 for non-profit plans) |
| `remaining_coverable`     | `abs(amount) − covered` (0 for non-loss plans)  |
| `allocations_balanced`    | allocation percentages sum to ~100 %            |

**Class method:** `calculate_amount(entity, period) → Decimal`
Sums INCOME_TYPES credited to `entity` and subtracts COST_TYPES debited from
`entity` within the period's operations.

```
INCOME: SALE, CAPITAL_GAIN, CORRECTION_CREDIT
COSTS:  EXPENSE, PURCHASE, CAPITAL_LOSS, CORRECTION_DEBIT
```

### ShareholderAllocation

| Field       | Type             | Notes                           |
|-------------|------------------|---------------------------------|
| plan        | FK → DistributionPlan | cascade delete             |
| shareholder | FK → Entity      | must have `is_shareholder=True` |
| percent     | DecimalField(6,3)| ≥ 0; no upper bound enforced   |

**Computed:** `instructional_amount = plan.amount × percent / 100` (rounded to 2 dp).

**Unique constraint:** one allocation per `(plan, shareholder)`.

### ProfitDistributionOperation (proxy of Operation)

| Direction      | Flow                                  |
|----------------|---------------------------------------|
| Issuance tx    | `project.fund → shareholder.fund`     |
| Payment tx     | `project.fund → shareholder.fund`     |

- One-shot, auto-settled (`is_fully_settled = True` on creation).
- Requires a `plan` with `is_profit = True`.
- `amount` must not exceed `plan.remaining_distributable`.
- Source must be a Project entity; destination must be a shareholder entity.
- Reversible; reversal restores `remaining_distributable`.

### LossCoverageOperation (proxy of Operation)

| Direction      | Flow                                  |
|----------------|---------------------------------------|
| Issuance tx    | `shareholder.fund → project.fund`     |
| Payment tx     | `shareholder.fund → project.fund`     |

- One-shot, auto-settled.
- Requires a `plan` with `is_loss = True`.
- `amount` must not exceed `plan.remaining_coverable`.
- Source must be a shareholder entity; destination must be a project entity.
- Reversible; reversal restores `remaining_coverable`.

---

## Tasks

### DistributionPlan — model & migration

- [x] Define `DistributionPlan` model (entity, period, amount, unique constraint)
- [x] Add `plan` FK to `Operation` model (nullable, PROTECT)
- [x] Define `ShareholderAllocation` model
- [x] Migration `0005_distribution_plan`
- [x] `is_profit` / `is_loss` properties
- [x] `distributed` / `covered` aggregate properties (exclude reversed ops)
- [x] `remaining_distributable` / `remaining_coverable` properties
- [x] `allocations_balanced` property
- [x] `calculate_amount(entity, period)` classmethod
- [x] `clean()` — entity must be a project
- [x] `clean()` — period must belong to the same entity
- [x] `clean()` — period must be closed
- [x] Immutability — entity, period, amount locked after save

### ShareholderAllocation — model

- [x] `instructional_amount` property
- [x] `clean()` — shareholder must have `is_shareholder=True`
- [x] `clean()` — percent cannot be negative

### ProfitDistributionOperation — proxy

- [x] `clean_source()` — source must be a Project entity
- [x] `clean_destination()` — destination must be a shareholder entity
- [x] `clean()` — plan required
- [x] `clean()` — plan must be a profit plan
- [x] `clean()` — amount must not exceed `remaining_distributable`
- [x] Reversal restores `remaining_distributable`
- [x] `get_related_entities()` — returns active shareholders of the project

### LossCoverageOperation — proxy

- [x] `clean()` — plan required
- [x] `clean()` — plan must be a loss plan
- [x] `clean()` — amount must not exceed `remaining_coverable`
- [x] Reversal restores `remaining_coverable`
- [x] `get_related_entities()` — returns projects where entity is a shareholder

### Tests

- [x] `DistributionPlanPropertiesTest` — is_profit, is_loss, distributed, covered, remaining_distributable, remaining_coverable, allocations_balanced, __str__
- [x] `DistributionPlanValidationTest` — entity must be project, period must match entity, period must be closed, unique constraint
- [x] `DistributionPlanImmutabilityTest` — amount, entity, period immutable
- [x] `DistributionPlanCalculateAmountTest` — zero, capital gain, capital loss, pure loss, cross-period isolation, multiple ops
- [x] `ShareholderAllocationTest` — instructional_amount, non-shareholder raises, negative percent raises, zero allowed, unique constraint, multiple shareholders
- [x] `ProfitDistributionOperationTest` — happy path, plan required, loss plan raises, break-even raises, amount cap, exceeds remaining after partial distribution, reversal restores remaining, destination must be shareholder
- [x] `LossCoverageOperationTest` — happy path, plan required, profit plan raises, amount cap, exceeds remaining after partial coverage, reversal restores remaining

### UI

- [ ] `DistributionPlan` list view per project
- [ ] `DistributionPlan` create form (pre-fills `calculate_amount`)
- [ ] `ShareholderAllocation` inline on plan detail
- [ ] `ProfitDistributionOperation` create form (plan selector filtered to profit plans)
- [ ] `LossCoverageOperation` create form (plan selector filtered to loss plans)
- [ ] Plan detail shows distributed/remaining and covered/remaining progress
- [ ] Reversal button on ProfitDistribution and LossCoverage operation detail
