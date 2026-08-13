# `<OP_NAME>` — Operation Contract

<!--
Template for widening an operation spec into a primary-source contract.

Worked example: specs/operations/op_1_cash_injection.md (Cash Injection).

Steps to widen a new operation:
  1. Read the operation's proxy class — copy every config flag into §1 (identity).
  2. Read the shared `Operation` engine, the base mixins/models, and the transaction
     types to confirm which shared engine clauses apply (immutability, one-shot,
     balance check, reversal guards, period rules).
  3. Read the create/reverse/pay view handlers, the validators, and the URL wiring
     to register the view contract.
  4. Read the operation's tests and map every branch to a pinning test. Add missing
     focused tests (one behavior per test, few assertions) until the coverage matrix
     in §10 is complete.
  5. Record every implementing concern in §2 (contract map). The spec is the primary
     source of contract: where code and spec disagree, fix the code, not the spec.
  6. Update the branch catalog (§9) and the test coverage matrix (§10).
-->

**Epic:** `<EPIC>` — `<SECTION>`
**Type:** `<one-shot / multi-stage / …>`
**Actions:** `<comma-separated: create, reverse, pay, repay, adjust, move items, adjust items>`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **`<OP_NAME>`** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_1_cash_injection.md`](op_1_cash_injection.md) for a fully worked example.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.<X>` | |
| Proxy class | `<X>Operation` | |
| URL slug | `"<x>"` | |
| Label | `"<X>"` | |
| Theme | `<color>` / `<icon>` | |
| Source role | `<world/system/url/post>` | |
| Destination role | `<world/system/url/post>` | |
| Registered in | `PROXY_MAP` | |
| Cross-op reference | row `<code>` | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags:**

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `<TX_ISSUANCE>` | … |
| `_payment_transaction_type` | `<TX_PAYMENT>` | … |
| `_repayment_transaction_type` | `<TX_REPAYMENT>` / n/a | … |
| `_is_one_shot_operation` | `<bool>` | … |
| `can_pay` | `<bool>` | … |
| `is_partially_payable` | `<bool>` | … |
| `max_payment_transaction_count` | `<int>` | … |
| `check_balance_on_payment` | `<bool>` | … |
| `has_category` / `category_required` | `<bool>` | … |
| `has_repayment` | `<bool>` | … |
| `has_invoice` | `<bool>` | … |
| `creates_assets` / `can_create_movement` | `<bool>` | … |
| `is_adjustable` / `is_items_adjustable` | `<bool>` | … |

---

## 2. Registered business logic (contract map)

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination` | |
| Proxy registry / URL→class resolution | |
| Shared `Operation` engine | |
| Operation type enum | |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability | `ImmutableMixin` |
| Amount > 0 | `AmountCleanMixin` |
| Officer staff + active | `OfficerMixin` |
| Source/target fund active | `SourceFundMixin` / `TargetFundMixin` |
| Issuance tx on save | `LinkedIssuanceTransactionMixin` |
| Payment / settlement | `LinkedPaymentTransactionMixin` |
| Repayment | `LinkedRePaymentTransactionMixin` (if `has_repayment`) |
| Reversal mechanics | `ReversableModel` + `Operation.reverse()` |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` + `reverse()` | |
| `<TX_ISSUANCE>` / `<TX_PAYMENT>` / … | |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derivation | `Entity.balance_at` |
| Virtual-entity payment exemption | `Entity.can_pay` |
| Open period auto-creation | `Entity.save()` |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view | `OperationCreateView` (or dedicated wizard) |
| POST parsing/validation | `OperationDataValidator` |
| Reverse view | `operation_reverse_view` |
| Pay / repay views | `record_transaction_*` (if applicable) |
| Detail view | `operation_detail_view` |
| URLs | |
| Templates | |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| `<action>` branches | |
| Coverage manifest | |

---

## 3. Money flow & entities

- **Source (payer):** …
- **Destination (receiver):** …
- **Transaction flow:** table of issuance / payment / repayment rows with directions and balance effects.

## 4. Settlement model

`amount_settled`, `total_settlable_amount`, `amount_remaining_to_settle`, `is_fully_settled` after each action.

---

## 5. Actions

### 5.1 `create`

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | … | … | `ValidationError` | `"…"` | [`code`](…) | [`test`](…) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | … | … | [`code`](…) | [`test`](…) |

### 5.2 `reverse`

(validation branches + success effects, as §5.1)

### 5.3 `pay`

(if a standalone pay action exists — balance per payment, partial allowed, over-payment guard, one-shot guard)

### 5.4 `repay`

(if `has_repayment` — repayable cap = min(total, amount_settled), over-repayment guard)

### 5.5 `adjust` / `adjust items` / `move items`

(only for Purchase/Sale/Expense-style ops — see operations-comparison.md)

### 5.6 Immutability

(source/destination/amount/period immutable after save)

---

## 6. Period & financial-period contract

(governing entity via `_source_role`/`_dest_role`, covering-period requirement, closed-period rejection, reversal exemption)

## 7. Entity roles & balance contract

(role constraints at model + transaction layers; which tx types move balance; virtual exemptions)

## 8. View / UI contract

(route, source/dest pickers, category, amount source, list entry, detail, reverse/pay/repay flows)

---

## 9. Branch catalog (all possible branches)

- **create — validation:** …
- **create — effects:** …
- **reverse — validation:** …
- **reverse — effects:** …
- **pay / repay / adjust / immutability:** …

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| … | [`test…`](…) | … |

## 11. Tasks

- [ ] … (one per branch/effect; mark `[x]` once pinned by a focused test)
