# Operations — Validation & Success-Effects Comparison (per action)

**Purpose:** Consolidated, cross-operation reference derived from the per-operation "eagle-eye" reviews (see `chats/`), the per-operation specs in this directory, and the implementation.

**Scope:** All 19 operation types.

**Structure:** Each operation is acted upon through a subset of **7 actions** — `create`, `reverse`, `adjust`, `move items`, `adjust items`, `pay`, `repay`. Validation checks and success effects are documented **per action** below, arranged per operation. Not every operation accepts every action (see [Action applicability](#action-applicability)).

---

## Actions

| # | Action | Meaning | Primary code path |
|---|--------|---------|-------------------|
| A1 | **create** | First save of the operation — establishes source/destination/amount/officer/period/plan and fires the issuance side-effects. | `Operation.create()` → `save()` → `full_clean()` (proxy `clean()` + `clean_source`/`clean_destination` + mixin cleans) → `post_save_tasks` |
| A2 | **reverse** | Reverse an operation — clones it, links via `reversal_of`, creates counter-transactions and negates ledger/movements. | `Operation.reverse()` → `ReversableModel.reverse()` |
| A3 | **adjust** | Accounting adjustment on the operation amount (only Purchase / Sale / Expense). | `Adjustment` → `record_accounting_adjustment` |
| A4 | **move items** | Inventory movement lines — user-driven receipt/dispatch (Purchase / Sale) or auto-created (Birth / Death / Consumption). | `InventoryMovementLine` → `create_inventory_movement` |
| A5 | **adjust items** | Invoice-item correction (qty / unit price) on Purchase / Sale. | `InvoiceItemAdjustment.finalize()` → `record_item_adjustment` |
| A6 | **pay** | Payment / settlement transaction (cash movement toward the receiver). Standalone after creation for Loan / Expense / Purchase / Sale; for one-shot operations it fires at creation. | `create_payment_transaction` → `record_transaction_payment` |
| A7 | **repay** | Repayment / collection transaction (cash movement back to the source). | `create_repayment_transaction` → `record_transaction_repayment` |

---

## Action applicability

Rows = operations. Columns = actions. **E** = applicable/enforced, **E@create** = the transaction/effect fires only at creation (no standalone post-create action), **B** = action exists but is restricted/blocked under conditions, **—** = not applicable.

| Op | Operation | create | reverse | adjust | move items | adjust items | pay | repay |
|----|-----------|--------|---------|--------|-----------|-------------|-----|-------|
| CI | Cash Injection | E | E | — | — | — | E@create | — |
| CW | Cash Withdrawal | E | E | — | — | — | E@create | — |
| PF | Project Funding | E | E | — | — | — | E@create | — |
| PR | Project Refund | E | E | — | — | — | E@create | — |
| CG | Capital Gain | E | E | — | — | — | E@create | — |
| CL | Capital Loss | E | E | — | — | — | E@create | — |
| IT | Internal Transfer | E | E | — | — | — | E@create | — |
| LN | Loan | E | B | — | — | — | E | E |
| WA | Worker Advance | E | B | — | — | — | E@create | E |
| EX | Expense | E | B | E | — | — | E | — |
| PU | Purchase | E | B | E | E | E | E | — |
| SA | Sale | E | B | E | E | E | E | —¹ |
| CC | Correction Credit | E | E | — | — | — | E@create | — |
| CD | Correction Debit | E | E | — | — | — | E@create | — |
| BI | Birth | E | E | — | E (auto) | — | E@create | — |
| DE | Death | E | E | — | E (auto) | — | E@create | — |
| CO | Consumption | E | B | — | — | — | E@create | — |

¹ Sale's **collection** is its pay action (`SALE_COLLECTION` is the payment transaction type; `has_repayment=False`) — folded into **pay**.

---

## Legend

### Validation matrix markers

| Marker | Meaning |
|--------|---------|
| **E** | Enforced — the check runs and rejects invalid input with `ValidationError`. |
| **E@create** | Enforced only at creation (e.g. one-shot balance check). |
| **X** | Exempt — deliberately skipped by design (system/world payer, admin correction tool, no-balance write-down, etc.). |
| **B** | Blocked — the action is refused under this condition (reversal / pay guards). |
| **N/A** | Not applicable — the parameter does not apply to this operation type / action. |
| **gap** | Not enforced due to a documented deficiency (all previously documented gaps have been resolved). |

### Success-effects matrix markers

| Marker | Meaning |
|--------|---------|
| **✓** | Yes — this effect occurs on a successful action. |
| **✗** | No — this effect does not occur. |
| **▼ / ▲** | Balance direction on the fund of the relevant party (cash movement). |
| **—** | Not a settlement-style outcome (tracked via repayment/collection instead) / not applicable. |

---

## Cross-cutting inventory guards (enforced on all inventory operations)

Implemented in the 2026-08 inventory-integrity pass (see [`ai-plans/inventory-integrity-fixes-plan.md`](../ai-plans/inventory-integrity-fixes-plan.md)). Applies to the `move items` / auto `move items` actions of Purchase, Sale, Birth, Death, Consumption (and product selection for Capital Gain/Loss).

| Guard | Enforced where | Behavior |
|-------|----------------|----------|
| **Ownership / location** | `InvoiceItemSelectForm` + `InventoryMovementLine.clean` + `Operation.save_inventory` | Outbound moves (SALE/DEATH/CONSUMPTION) reject a product not owned by the affected project; select forms filter to the owning entity. |
| **Availability** | `InventoryMovementLine.clean` + auto-create path | Outbound moves cannot exceed the product's physically-present on-hand (ledger `state_as_of`). SALE products created at sale time (never received) are exempt. |
| **Unit consistency** | `InventoryMovementLine.clean` + `InvoiceItem.clean` | Quantity must be a positive multiple of `product_template.minimum_quantity` (1 for Head, 0.01 for Kg). |
| **Positive quantity** | model validators (`MinValueValidator(0.01)`, `AmountCleanMixin`) | Quantity/amounts must be > 0. |
| **Status eligibility** | `Product.validate_active` | SOLD/DEAD/CONSUMED products are blocked from new operations; obligated-only products blocked from downstream ops unless `allow_obligated`. |
| **Product–operation compatibility** | `InvoiceItem.clean` / `Product.clean` via `accepts_operation` | Nature↔operation matrix (ANIMAL can't be consumed; FEED/MEDICINE can't be born/died). |
| **Closed period** | payment/repayment mixins + movement & adjustment views | Payments, repayments, movements and adjustments whose date falls inside a closed financial period are rejected. |
| **Concurrency** | `Product.lock_ids` / `select_for_update` | Product rows and payer funds are locked during availability/balance checks (no-op on SQLite). |
| **Lifecycle on reversal** | `Product.status` | Reversing a Death/Sale/Consumption restores the product to ACTIVE (reversal-aware status). |
| **Reversal dependency** | `Operation.reverse` | Reversing an outbound op is blocked if its products were moved again in a later non-reversed outbound operation. |
| **Identity (Birth)** | form + `UniqueConstraint(entity, unique_id)` | INDIVIDUAL tracking requires a unique tag per entity. |
| **Valuation** | `valuation_unit_cost()` | Outbound movements are valued at the product's carried cost (purchase price). Other methods (moving average/FIFO) may be added later. |

These guards are omitted from each per-operation action below for brevity; treat the rows below as **financial-behavior** summaries.

## Operation reference

| # | Code | Operation | Proxy class | Spec |
|---|------|-----------|-------------|------|
| 1 | CI | Cash Injection | `CashInjectionOperation` | [op_1](op_1_cash_injection.md) |
| 2 | CW | Cash Withdrawal | `CashWithdrawalOperation` | [op_2](op_2_cash_withdrawal.md) |
| 3 | PF | Project Funding | `ProjectFundingOperation` | [op_3](op_3_project_funding.md) |
| 4 | PR | Project Refund | `ProjectRefundOperation` | [op_4](op_4_project_refund.md) |
| 5 | CG | Capital Gain | `CapitalGainOperation` | [op_5](op_5_capital_gain.md) |
| 6 | CL | Capital Loss | `CapitalLossOperation` | [op_6](op_6_capital_loss.md) |
| 7 | IT | Internal Transfer | `InternalTransferOperation` | [op_7](op_7_internal_transfer.md) |
| 8 | LN | Loan | `LoanOperation` | [op_8](op_8_loan.md) |
| 11 | WA | Worker Advance | `WorkerAdvanceOperation` | [op_11](op_11_worker_advance.md) |
| 12 | EX | Expense | `ExpenseOperation` | [op_12](op_12_expense.md) |
| 13 | PU | Purchase | `PurchaseOperation` | [op_13](op_13_purchase.md) |
| 14 | SA | Sale | `SaleOperation` | [op_14](op_14_sale.md) |
| 15 | CC | Correction Credit | `CorrectionCreditOperation` | [op_15](op_15_correction.md) |
| 16 | CD | Correction Debit | `CorrectionDebitOperation` | [op_15](op_15_correction.md) |
| 17 | BI | Birth | `BirthOperation` | [op_17](op_17_birth.md) |
| 18 | DE | Death | `DeathOperation` | [op_18](op_18_death.md) |
| 19 | CO | Consumption | `ConsumptionOperation` | [op_19](op_19_consumption.md) |

---

## Per-operation reference (validation + effects, condensed)

Each operation lists its applicable **actions**, each with the condensed validation checks and success effects. Markers follow the [Legend](#legend).

**Apply to all operations (omitted per action below):**
- **create** — both parties active; fund active; amount > 0; officer present — all enforced (E).
- **reverse** — not already reversed; not a reversal; reason required.

### 1. Cash Injection (CI) — `CashInjectionOperation` — [op_1](op_1_cash_injection.md)

Actions: create, reverse.
- **create** — *Valid:* source=world; dest=person; balance ✗ (world exempt); one-shot auto-settled. *Effects:* `CASH_INJECTION_ISSUANCE` + `CASH_INJECTION_PAYMENT`; immediately settled; ▼world → ▲person; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 2. Cash Withdrawal (CW) — `CashWithdrawalOperation` — [op_2](op_2_cash_withdrawal.md)

Actions: create, reverse.
- **create** — *Valid:* source=person; dest=world; balance E; one-shot auto-settled. *Effects:* `CAPITAL_WITHDRAWAL_ISSUANCE` + `CAPITAL_WITHDRAWAL_PAYMENT`; immediately settled; ▼person → ▲world; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 3. Project Funding (PF) — `ProjectFundingOperation` — [op_3](op_3_project_funding.md)

Actions: create, reverse.
- **create** — *Valid:* source=person (shareholder of dest project); dest=project; balance E (clean()); one-shot auto-settled. *Effects:* `PROJECT_FUNDING_ISSUANCE` + `PROJECT_FUNDING_PAYMENT`; immediately settled; ▼funder → ▲project; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 4. Project Refund (PR) — `ProjectRefundOperation` — [op_4](op_4_project_refund.md)

Actions: create, reverse.
- **create** — *Valid:* source=project; dest=shareholder; balance E (clean()); one-shot auto-settled; **extra:** amount ≤ `total_funded − total_refunded`. *Effects:* `PROJECT_REFUND_ISSUANCE` + `PROJECT_REFUND_PAYMENT`; immediately settled; ▼project → ▲shareholder; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 5. Capital Gain (CG) — `CapitalGainOperation` — [op_5](op_5_capital_gain.md)

Actions: create, reverse.
- **create** — *Valid:* source=system; dest=project (E, `clean_source`/`clean_destination`); balance ✗ (system exempt); one-shot auto-settled. *Effects:* `CAPITAL_GAIN_ISSUANCE` + `CAPITAL_GAIN_PAYMENT` (non-cash — excluded from `payment_types()`); immediately settled; **no cash flow** — ▼system → ▲project (inventory value only); ✓ value-only ledger (qty 0, value +); status unchanged (ACTIVE).
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment; negated ledger.

### 6. Capital Loss (CL) — `CapitalLossOperation` — [op_6](op_6_capital_loss.md)

Actions: create, reverse.
- **create** — *Valid:* source=entity; dest=system; balance ✗ (no-balance write-down, may go into deficit); one-shot auto-settled; verified: source fund must NOT have sufficient balance (loss can deepen deficit). *Effects:* `CAPITAL_LOSS_ISSUANCE` + `CAPITAL_LOSS_PAYMENT` (non-cash — excluded from `payment_types()`); immediately settled; **no cash flow** — ▼entity → ▲system (inventory value only); ✓ value-only ledger (qty 0, value −); status unchanged (ACTIVE).
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment; negated ledger.

### 7. Internal Transfer (IT) — `InternalTransferOperation` — [op_7](op_7_internal_transfer.md)

Actions: create, reverse.
- **create** — *Valid:* source & dest internal (not system/world); src≠dst; balance E (clean()); one-shot auto-settled. *Effects:* `INTERNAL_TRANSFER_ISSUANCE` + `INTERNAL_TRANSFER_PAYMENT`; immediately settled; ▼fund A → ▲fund B; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 8. Loan (LN) — `LoanOperation` — [op_8](op_8_loan.md)

Actions: create, reverse, pay, repay.
- **create** — *Valid:* source/dest person|project; src≠dst; balance ✗ (issuance unguarded); multi-stage (not one-shot). *Effects:* `LOAN_ISSUANCE` (non-cash); no payment at save.
- **pay** — *Valid:* balance E per disbursement; amount>0 & ≤ remaining; partial E (multiple disbursements); over-payment guard. *Effects:* `LOAN_PAYMENT`; ▼creditor → ▲debtor; amount_settled ↑.
- **repay** — *Valid:* amount>0 & ≤ remaining; over-repayment guard. *Effects:* `LOAN_REPAYMENT`; ▼debtor → ▲creditor; amount_repayed ↑.
- **reverse** — *Valid:* blocked if any disbursement; blocked if outstanding repayments. *Effects:* reversal record; counter-tx for issuance only.

### 11. Worker Advance (WA) — `WorkerAdvanceOperation` — [op_11](op_11_worker_advance.md)

Actions: create, reverse, repay.
- **create** — *Valid:* source=project; dest=active worker; balance E (clean()); one-shot (issuance + payment pair). *Effects:* `WORKER_ADVANCE_ISSUANCE` + `WORKER_ADVANCE_PAYMENT`; repayment-tracked (not immediately settled); ▼project → ▲worker.
- **repay** — *Valid:* amount>0 & ≤ remaining; over-repayment guard. *Effects:* `WORKER_ADVANCE_REPAYMENT`; ▼worker → ▲project; amount_repayed ↑.
- **reverse** — *Valid:* blocked if any repayment. *Effects:* reversal record; counter-tx for issuance + payment.

### 12. Expense (EX) — `ExpenseOperation` — [op_12](op_12_expense.md)

Actions: create, reverse, adjust, pay.
- **create** — *Valid:* source=project; dest=world; balance ✗ (issuance unguarded); category required (EXPENSE type, model-level FK enforced); not one-shot. *Effects:* `EXPENSE_ISSUANCE` (non-cash); no payment at save; no ledger; no movements.
- **pay** — *Valid:* balance E per payment; amount>0 & ≤ remaining; partial E; over-payment guard. *Effects:* `EXPENSE_PAYMENT`; ▼project → ▲world; amount_settled ↑.
- **adjust** — *Valid:* can_adjust; not reversed; type allowed for op; amount>0; officer staff + active; reduction can't drive below zero. *Effects:* `EXPENSE_ADJUSTMENT_INCREASE` / `EXPENSE_ADJUSTMENT_DECREASE` (non-cash); effective_amount delta.
- **reverse** — *Valid:* blocked if payments; blocked if adjustments. *Effects:* reversal record; counter-tx for issuance only.

### 13. Purchase (PU) — `PurchaseOperation` — [op_13](op_13_purchase.md)

Actions: create, reverse, adjust, move items, adjust items, pay.
- **create** — *Valid:* source=project; dest=active vendor; balance ✗ (issuance unguarded); not one-shot. *Effects:* `PURCHASE_ISSUANCE` (non-cash); no payment at save; ✓ issuance ledger entry; status ACTIVE.
- **pay** — *Valid:* balance E per payment; amount>0 & ≤ remaining; partial E; over-payment guard. *Effects:* `PURCHASE_PAYMENT`; ▼project → ▲vendor; amount_settled ↑.
- **move items** — *Valid:* not reversed; qty ≤ item remaining qty; product allowed (active/obligated); officer staff + active; template compatible. *Effects:* `PURCHASE_MOVEMENT` ledger; lazy product creation; status ACTIVE; remaining qty ↓.
- **adjust items** — *Valid:* not reversed; ≥1 item changed; new qty/price parse; new qty ≥ already moved; finalize checks. *Effects:* ItemAdj + lines; adjusted qty/price; accounting Adjustment + tx; ledger `*_ADJUSTMENT` entries.
- **adjust** — *Valid:* can_adjust; not reversed; type allowed for op; amount>0; officer staff + active; reduction can't drive below zero. *Effects:* `PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE` (non-cash); effective_amount delta.
- **reverse** — *Valid:* blocked if payments; blocked if user movements; blocked if adjustments. *Effects:* reversal record; counter-tx for issuance only; negated ledger.

### 14. Sale (SA) — `SaleOperation` — [op_14](op_14_sale.md)

Actions: create, reverse, adjust, move items, adjust items, pay.
- **create** — *Valid:* source=active client; dest=project; balance ✗ (issuance unguarded); not one-shot. *Effects:* `SALE_ISSUANCE` (non-cash receivable); no payment at save; ✓ issuance ledger entry; status SOLD.
- **pay** (the **collection**) — *Valid:* balance E per collection; amount>0 & ≤ remaining; partial E; over-payment guard. *Effects:* `SALE_COLLECTION`; ▼client → ▲project; amount_settled ↑.
- **move items** — *Valid:* not reversed; qty ≤ item remaining qty; product allowed (active/obligated); officer staff + active; template compatible; ownership (belongs to selling project); availability (≤ on-hand for received stock); unit multiple. *Effects:* `SALE_MOVEMENT` ledger (carried cost); status SOLD; remaining qty ↓.
- **adjust items** — *Valid:* not reversed; ≥1 item changed; new qty/price parse; new qty ≥ already moved; finalize checks. *Effects:* ItemAdj + lines; adjusted qty/price; accounting Adjustment + tx; ledger `*_ADJUSTMENT` entries.
- **adjust** — *Valid:* can_adjust; not reversed; type allowed for op; amount>0; officer staff + active; reduction can't drive below zero. *Effects:* `SALE_ADJUSTMENT_INCREASE` / `SALE_ADJUSTMENT_DECREASE` (non-cash); effective_amount delta.
- **reverse** — *Valid:* blocked if collections; blocked if user movements; blocked if adjustments; reversal dependency guard. *Effects:* reversal record; counter-tx for issuance only; negated ledger; product status restored to ACTIVE.

### 15. Correction Credit (CC) — `CorrectionCreditOperation` — [op_15](op_15_correction.md)

Actions: create, reverse.
- **create** — *Valid:* source=system; dest=project; balance ✗ (system exempt); one-shot auto-settled. *Effects:* `CORRECTION_CREDIT_ISSUANCE` + `CORRECTION_CREDIT_PAYMENT`; immediately settled; ▼system → ▲project; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 16. Correction Debit (CD) — `CorrectionDebitOperation` — [op_15](op_15_correction.md)

Actions: create, reverse.
- **create** — *Valid:* source=project; dest=system; balance ✗ (admin tool — can go into deficit); one-shot auto-settled. *Effects:* `CORRECTION_DEBIT_ISSUANCE` + `CORRECTION_DEBIT_PAYMENT`; immediately settled; ▼project → ▲system; no ledger; no movements.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment.

### 17. Birth (BI) — `BirthOperation` — [op_17](op_17_birth.md) — Inventory/Livestock

Actions: create, move items (auto), reverse.
- **create** — *Valid:* source=system; dest=project (E, `clean_source`/`clean_destination`); balance ✗ (system exempt); one-shot auto-settled; identity (INDIVIDUAL tracking requires a unique tag). *Effects:* `BIRTH_ISSUANCE` + `BIRTH_PAYMENT` (non-cash — excluded from `payment_types()`); immediately settled; **no cash flow** — ▼system → ▲project assets (inventory value only); issuance + auto movement; status ACTIVE (new asset).
- **move items** (auto) — *Valid:* qty ≤ remaining; unit multiple. *Effects:* `BIRTH_MOVEMENT` ledger (auto inbound, new-asset cost); lazy product creation; status ACTIVE.
- **reverse** — *Valid:* (constants). *Effects:* reversal record; counter-tx for issuance + payment; negated ledger; auto lines reversed.

### 18. Death (DE) — `DeathOperation` — [op_18](op_18_death.md) — Inventory/Livestock

Actions: create, move items (auto), reverse.
- **create** — *Valid:* source=project; dest=system; balance ✗ (no-balance write-off); one-shot auto-settled; availability (≤ on-hand); ownership (product belongs to source project). *Effects:* `DEATH_ISSUANCE` + `DEATH_PAYMENT` (non-cash — excluded from `payment_types()`); immediately settled; **no cash flow** — ▼project assets → ▲system (inventory value only); issuance + auto movement; status DEAD.
- **move items** (auto) — *Valid:* qty ≤ remaining; availability (≤ on-hand); ownership; unit multiple. *Effects:* `DEATH_MOVEMENT` ledger (auto outbound, carried cost); status DEAD.
- **reverse** — *Valid:* (constants); reversal dependency guard. *Effects:* reversal record; counter-tx for issuance + payment; negated ledger; auto lines reversed; product status restored to ACTIVE.

### 19. Consumption (CO) — `ConsumptionOperation` — [op_19](op_19_consumption.md) — Inventory/Livestock

Actions: create, reverse.
- **create** — *Valid:* source=project; dest=system; balance ✗ (no-balance write-off); one-shot auto-settled; availability (≤ on-hand); ownership (product belongs to source project). *Effects:* `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT`; immediately settled; **non-cash (payment is not a payment type — fund balance unchanged)**; `CONSUMPTION_ISSUANCE` counted as **COGS** in `Entity.profit_loss()` (reduces the project's P&L); issuance + auto movement lines; status CONSUMED.
- **reverse** — *Valid:* (constants); reversal dependency guard. *Effects:* reversal record; counter-tx for issuance + payment; negated ledger; auto lines reversed; product status restored to ACTIVE; **COGS negated (P&L restored); fund balance unchanged**.

---
