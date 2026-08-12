# Loan — Operation Contract

**Epic:** 12.1 — Repayable Operations
**Type:** Multi-stage, repayable (`has_repayment=True`, `max_payment_count=-1`)
**Actions:** `create`, `pay`, `repay`, `reverse`
**Contract status:** v2 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Loan** operation.
> Every clause below is registered to its implementing code (model → mixin → transaction → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Other operations follow the same structure — see [`_OPERATION_SPEC_TEMPLATE.md`](_OPERATION_SPEC_TEMPLATE.md).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Operation type | `OperationType.LOAN` (`"LOAN"`) | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:12) |
| Proxy class | `LoanOperation` | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:10) |
| URL slug | `"loan"` | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:16) |
| Label | `"Debt Issuance"` | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:17) |
| Theme | `danger` / `bi-box-arrow-up-right` (defaults, not overridden) | [`operation.py`](../../apps/app_operation/models/operation.py:112) |
| Source role | `url` (must be a Person or Project) | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:18) |
| Destination role | `post` (must be a Person or Project) | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:19) |
| Registered in | `PROXY_MAP` | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:33) |
| Cross-op reference | row LN | [`operations-comparison.md`](operations-comparison.md) |

**Configuration flags** (all on [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:10)):

| Flag | Value | Meaning |
|------|-------|---------|
| `_issuance_transaction_type` | `LOAN_ISSUANCE` | issuance (memo) tx created on save |
| `_payment_transaction_type` | `LOAN_PAYMENT` | disbursement tx created via **pay** (not on save) |
| `_repayment_transaction_type` | `LOAN_REPAYMENT` | repayment tx created via **repay** |
| `is_repayable` | `True` | repayment action enabled |
| `_is_one_shot_operation` | `False` | multi-stage: no payment at save; standalone pay action |
| `can_pay` | `False` | `process_payment()` is a no-op; payments created standalone |
| `is_partially_payable` | `False` | settlement driven by remaining; not a one-shot equality |
| `max_payment_transaction_count` | `-1` | unlimited partial disbursements |
| `check_balance_on_payment` | `True` | each disbursement is balance-checked at pay time |
| `has_category` / `category_required` | `False` | no financial category |
| `has_repayment` / `repayment_label` | `True` / `"Loan Recovery"` | repay action present |
| `has_invoice` | `False` | no invoice items / no inventory movements |
| `is_adjustable` | `False` | no accounting adjustment action |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this operation**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Model / config layer

| Concern | Implementing code |
|---------|-------------------|
| Proxy class + type-specific config + `clean_source`/`clean_destination`/`clean` | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:10) |
| Proxy registry / URL→class resolution | [`proxies/__init__.py`](../../apps/app_operation/models/proxies/__init__.py:33) |
| Shared `Operation` engine (`clean`, `save`, `reverse`, `create`, `resolve_request`, period assignment, reversable tx types) | [`operation.py`](../../apps/app_operation/models/operation.py:34) |
| Operation type enum | [`operation_type.py`](../../apps/app_operation/models/operation_type.py:12) |

### 2.2 Core engine (mixins / base)

| Concern | Implementing code |
|---------|-------------------|
| Immutability of `source`/`destination`/`amount`/`period` | [`ImmutableMixin`](../../apps/app_base/mixins.py:30) + `_immutable_fields` in [`operation.py`](../../apps/app_operation/models/operation.py:51) |
| Amount must be > 0 | [`AmountCleanMixin`](../../apps/app_base/mixins.py:64) |
| Officer must be staff + active | [`OfficerMixin`](../../apps/app_base/mixins.py:80) |
| Source fund exists + active | [`SourceFundMixin`](../../apps/app_base/mixins.py:127) |
| Target fund exists + active | [`TargetFundMixin`](../../apps/app_base/mixins.py:147) |
| Issuance tx creation on save | [`LinkedIssuanceTransactionMixin`](../../apps/app_base/mixins.py:184) |
| Disbursement / settlement (`amount_settled`, balance check per payment) | [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) |
| Repayment (`amount_repayed`, cap by disbursed, over-repayment guard) | [`LinkedRePaymentTransactionMixin`](../../apps/app_base/mixins.py:463) |
| Reversal mechanics (clone, `reversal_of`, implicit tx reversal, guards) | [`ReversableModel`](../../apps/app_base/models.py:133) + [`Operation.reverse()`](../../apps/app_operation/models/operation.py:997) |

### 2.3 Transaction layer

| Concern | Implementing code |
|---------|-------------------|
| `Transaction` model + `create()` (entity-type + operation-type guards) + `reverse()` | [`models.py`](../../apps/app_transaction/models.py:33) |
| `LOAN_ISSUANCE` (creditor → debtor, non-cash) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:262), entity map [:538](../../apps/app_transaction/transaction_type.py:538), op map [:623](../../apps/app_transaction/transaction_type.py:623) |
| `LOAN_PAYMENT` (creditor → debtor, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:269), entity map [:539](../../apps/app_transaction/transaction_type.py:539), op map [:624](../../apps/app_transaction/transaction_type.py:624), payment set [:435](../../apps/app_transaction/transaction_type.py:435) |
| `LOAN_REPAYMENT` (debtor → creditor, affects balance) | [`transaction_type.py`](../../apps/app_transaction/transaction_type.py:276), entity map [:540](../../apps/app_transaction/transaction_type.py:540), op map [:625](../../apps/app_transaction/transaction_type.py:625), payment set [:436](../../apps/app_transaction/transaction_type.py:436) |

### 2.4 Entity / balance layer

| Concern | Implementing code |
|---------|-------------------|
| Balance derived from payment-type txs (`LOAN_PAYMENT`, `LOAN_REPAYMENT`) | [`Entity.balance_at`](../../apps/app_entity/models/__init__.py:414) |
| Real (non-virtual) funds balance-checked | [`Entity.can_pay`](../../apps/app_entity/models/__init__.py:704) |
| Open financial period auto-created on entity creation | [`Entity.save()`](../../apps/app_entity/models/__init__.py:714) |

### 2.5 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create view (generic, URL source + secondary-entity destination picker) | [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| POST parsing/validation | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) |
| Pay view (disbursement) | [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) |
| Repay view | [`record_transaction_repayment`](../../apps/app_operation/views/record_transaction.py:137) |
| Reverse view (reason required) | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) |
| Detail view (transactions + outstanding balance + pay/repay/reverse buttons) | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) |
| URL: `/<pk>/loan/create` | [`urls.py`](../../apps/app_operation/urls.py:144) |
| URL: `payment/<pk>/create` | [`urls.py`](../../apps/app_operation/urls.py:153) |
| URL: `repayment/<pk>/create` | [`urls.py`](../../apps/app_operation/urls.py:148) |
| URL: `/<pk>/detail/` | [`urls.py`](../../apps/app_operation/urls.py:184) |
| URL: `/<pk>/reverse/` | [`urls.py`](../../apps/app_operation/urls.py:194) |
| Templates | [`generic_form.html`](../../apps/app_operation/templates/app_operation/generic_form.html), [`add_payment_form.html`](../../apps/app_operation/templates/app_operation/add_payment_form.html), [`reverse_form.html`](../../apps/app_operation/templates/app_operation/reverse_form.html), [`operation_detail.html`](../../apps/app_operation/templates/app_operation/operation_detail.html), entry link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |

### 2.6 Tests

| Concern | Test file |
|---------|-----------|
| Create branches (issuance, validation, immutability) | [`test_loan_loan_create.py`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py) |
| Pay (disbursement) branches | [`test_loan_loan_disbursement.py`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py) |
| Repay branches | [`test_loan_loan_repayment.py`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py) |
| Reverse branches | [`test_loan_loan_reversal.py`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py) |
| Coverage manifest (executable branch registry) | [`tests/base.py`](../../apps/app_operation/tests/base.py:490) |

---

## 3. Money flow & entities

- **Source (creditor / payer):** the **Person or Project** entity in the URL (`_source_role="url"`). Its fund is the payment source fund — the real payer for disbursements.
- **Destination (debtor / receiver):** a **Person or Project** entity (`_dest_role="post"` — secondary-entity picker, `get_related_entities`). Its fund is the payment target fund.
- **Transaction flow:**

| # | Type | Direction | Balance effect |
|---|------|-----------|----------------|
| 1 | `LOAN_ISSUANCE` | `creditor.fund → debtor.fund` | none (issuance, non-cash memo) |
| 2 | `LOAN_PAYMENT` | `creditor.fund → debtor.fund` | ▼ creditor fund, ▲ debtor fund, ▲ creditor receivables, ▲ debtor payables |
| 3 | `LOAN_REPAYMENT` | `debtor.fund → creditor.fund` | ▲ creditor fund, ▼ debtor fund, ▼ creditor receivables, ▼ debtor payables |

- **Payment source fund:** `self.source` (creditor) — [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:37)
- **Payment target fund:** `self.destination` (debtor) — [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:41)

> **World / System exclusion.** The World and System entities can never be a side of a loan: both `clean_source()` and `clean_destination()` require Person or Project, and the transaction entity map uses `not_virtual` for both sides ([`transaction_type.py`](../../apps/app_transaction/transaction_type.py:538)).

---

## 4. Settlement model

### 4.1 Payment settlement (disbursements)

Derived from [`LinkedPaymentTransactionMixin`](../../apps/app_base/mixins.py:242) using `LOAN_PAYMENT` only:

| Property | After create | After each pay | After full pay |
|----------|--------------|----------------|----------------|
| `amount_settled` | `0.00` | `∑ LOAN_PAYMENT` | `== amount` |
| `total_settlable_amount` | `== amount` | unchanged | unchanged |
| `amount_remaining_to_settle` | `== amount` | `amount − settled` | `0.00` |
| `is_fully_settled` | `False` | depends | `True` |

### 4.2 Repayment model

Derived from [`LinkedRePaymentTransactionMixin`](../../apps/app_base/mixins.py:463) using `LOAN_REPAYMENT` only:

| Property | Formula / behavior | Defined in |
|----------|--------------------|-----------|
| `repayable_amount` | `min(total_repayable_amount, amount_settled)` — capped by the disbursed amount | [`mixins.py`](../../apps/app_base/mixins.py:480) |
| `amount_repayed` | net `LOAN_REPAYMENT` flow toward the creditor fund (reversals netted out) | [`mixins.py`](../../apps/app_base/mixins.py:492) |
| `amount_remaining_to_repay` | `repayable_amount − amount_repayed` | [`mixins.py`](../../apps/app_base/mixins.py:511) |
| `is_fully_repayed` | `amount_repayed >= repayable_amount` | [`mixins.py`](../../apps/app_base/mixins.py:515) |

**Key rule:** a loan with **no disbursement** is not repayable — `repayable_amount` is `0` because `amount_settled` is `0`. Repayments can never exceed the total disbursed (`∑ LOAN_PAYMENT`), even if the loan agreement (`amount`) is larger.

---

## 5. Actions

### 5.1 `create`

Entry points: model `LoanOperation.save()` (tests) or `Operation.create()` (view). Both converge on `save()` → `full_clean()` → `post_save_tasks` (issuance tx only — no payment).

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Source (creditor) is Person or Project | `source.is_person or source.is_project` | `ValidationError` | `"Loan source (creditor) must be a Person or Project entity."` | [`clean_source`](../../apps/app_operation/models/proxies/op_loan.py:52) | [`test_source_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:198), [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:192) |
| VC2 | Destination (debtor) is Person or Project | `destination.is_person or destination.is_project` | `ValidationError` | `"Loan destination (debtor) must be a Person or Project entity."` | [`clean_destination`](../../apps/app_operation/models/proxies/op_loan.py:58) | [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:203), [`test_destination_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:208) |
| VC3 | Source entity active | `source.active` | `ValidationError` | `"Entity '%(name)s' must be active…"` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:143) |
| VC4 | Destination entity active | `destination.active` | `ValidationError` | same as VC3 | [`Operation.clean()`](../../apps/app_operation/models/operation.py:528) | [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:163) |
| VC5 | Source fund active | `payment_source_fund.active` | `ValidationError` | `"The Payment source entity should be active."` | [`SourceFundMixin`](../../apps/app_base/mixins.py:132) | merged with VC3 ([`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:151)) |
| VC6 | Target fund active | `payment_target_fund.active` | `ValidationError` | `"The Payment target entity should be active."` | [`TargetFundMixin`](../../apps/app_base/mixins.py:152) | merged with VC4 |
| VC7 | Amount positive | `amount > 0` | `ValidationError` | `"Amount should be positive, got …"` | [`AmountCleanMixin`](../../apps/app_base/mixins.py:69) | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:227), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:232) |
| VC8 | Officer is staff | `officer.is_staff` | `ValidationError` | `"Officer should be a staff user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:81) | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:241) |
| VC9 | Officer active | `officer.is_active` | `ValidationError` | `"Officer should be an active user."` | [`OfficerMixin`](../../apps/app_base/mixins.py:84) | [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:249) |
| VC10 | Date not in a closed period (both entities) | no closed period contains `date` | `ValidationError` | `"Cannot create an operation whose date falls within a closed financial period."` | [`Operation.clean()`](../../apps/app_operation/models/operation.py:541) | covered by period suite |
| VC11 | A covering financial period exists | `period_entity` has a period containing `date` | `ValidationError` | `"Cannot create an operation: no financial period covers this operation's date."` | [`Operation.save()`](../../apps/app_operation/models/operation.py:595) | covered by period suite |
| VC12 | Balance exempt at create | issuance is unguarded; balance check deferred to each disbursement | never fails at create | — | `check_balance_on_payment=True` (only at pay) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:291), [`test_amount_remaining_to_repay_is_zero_without_disbursement`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:107) |
| VC13 | Tx entity-type contract | both sides non-virtual (Person or Project) | `ValidationError` | `"Transaction type '…' has invalid entity types: …"` | [`Transaction.create()`](../../apps/app_transaction/models.py:144) + map [:538](../../apps/app_transaction/transaction_type.py:538) | implied by VC1/VC2 (model clean blocks first) |
| VC14 | Tx operation-type allowed | document is `LOAN` | `ValidationError` | `"Transaction type '…' is not allowed for operation '…'."` | [`Transaction.create()`](../../apps/app_transaction/models.py:155) + map [:623](../../apps/app_transaction/transaction_type.py:623) | implied by VC1/VC2 |
| VC15 | Source ≠ destination | `source_id != destination_id` | `ValidationError` | `"Loan source (creditor) and destination (debtor) must be different entities."` | [`clean()`](../../apps/app_operation/models/proxies/op_loan.py:64) | [`test_source_and_destination_must_be_different`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:218) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Issuance tx created | 1 × `LOAN_ISSUANCE`, amount `== op.amount`, `creditor → debtor` (non-cash memo) | [`LinkedIssuanceTransactionMixin.save()`](../../apps/app_base/mixins.py:222) | [`test_creates_issuance_transaction_on_save`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:85) |
| SC2 | Issuance direction | `source=creditor`, `target=debtor` | transaction creation | [`test_issuance_transaction_direction_is_creditor_to_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:92) |
| SC3 | Issuance amount equals op amount | `tx.amount == op.amount` | transaction creation | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:100) |
| SC4 | No payment on save | multi-stage: only `LOAN_ISSUANCE` exists; disbursements happen later via **pay** | `_is_one_shot_operation=False` | [`test_creates_issuance_transaction_on_save`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:85) (asserts only `LOAN_ISSUANCE: 1`) |
| SC5 | No balance effect at create | issuance is a non-payment type; no fund/receivable/payable change | issuance_types (`LOAN_ISSUANCE`) | module contract ([`test_loan_loan_create.py`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:46)) |
| SC6 | Not repayable before disbursement | `amount_remaining_to_repay == 0` with no `LOAN_PAYMENT` | `repayable_amount` cap | [`test_amount_remaining_to_repay_is_zero_without_disbursement`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:107) |
| SC7 | `creditor`/`debtor` aliases | `creditor == source`, `debtor == destination` | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:44) | [`test_creditor_property`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:118), [`test_debtor_property`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:124) |
| SC8 | Person or Project allowed on either side | any combination of Person/Project accepted | `clean_source`/`clean_destination` | [`test_project_as_creditor_person_as_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:130), [`test_source_can_be_person_or_project`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:175), [`test_source_vendor_person_is_still_a_valid_creditor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:184) |

### 5.2 `pay` (disbursement)

Entry point: model `op.create_payment_transaction(amount, officer, date)` or view `record_transaction_payment` (`POST payment/<pk>/create`).

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VP1 | Balance enforced per disbursement | `payment_source_fund.can_pay(amount)` | `ValidationError` | `"Insufficient funds: fund balance (%(balance)s) is less than the payment amount (%(amount)s)."` | [`create_payment_transaction()`](../../apps/app_base/mixins.py:377) | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:291) |
| VP2 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:318) | n/a (shared engine) |
| VP3 | Amount ≤ remaining | `amount <= amount_remaining_to_settle` | `ValidationError` | `"The paid amount %(amount)s exceeds the remaining: %(remaining)s"` | [`validate_settlement_amount`](../../apps/app_base/mixins.py:320) | over-payment guard (shared engine) |
| VP4 | Partial disbursements allowed | unlimited (`max_payment_transaction_count=-1`) | never fails | — | [`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:30) | [`test_multiple_payment_disbursements_allowed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:124) |
| VP5 | Closed-period guard on payment date | governing period open on `date` | `ValidationError` | `"Cannot record a payment dated within a closed financial period."` | [`create_payment_transaction()`](../../apps/app_base/mixins.py:370) | covered by period suite |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SP1 | `LOAN_PAYMENT` created | `creditor.fund → debtor.fund`, type `LOAN_PAYMENT` | [`create_payment_transaction()`](../../apps/app_base/mixins.py:355) | [`test_payment_creates_loan_payment_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:75) |
| SP2 | Payment direction | `source=creditor`, `target=debtor` | payment source/target funds | [`test_payment_transaction_direction_is_creditor_to_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:87) |
| SP3 | Creditor fund ▼ amount | `creditor.balance` decreases by `amount` | `Entity.balance_at` | [`test_creditor_fund_decreases_after_payment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:98) |
| SP4 | Debtor fund ▲ amount | `debtor.balance` increases by `amount` | `Entity.balance_at` | [`test_debtor_fund_increases_after_payment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:111) |
| SP5 | Debtor payables ▲ | `debtor.payables` increases by `amount` | payables derivation | [`test_payment_increases_debtor_payables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:145) |
| SP6 | Creditor receivables ▲ | `creditor.receivables` increases by `amount` | receivables derivation | [`test_payment_increases_creditor_receivables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:155) |
| SP7 | Other obligation buckets zero | creditor payables & debtor receivables stay `0` | obligation derivation | [`test_payment_leaves_other_obligation_buckets_zero`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:165) |
| SP8 | `amount_settled` ↑ | settlement grows by the disbursed amount | `amount_settled` | implied by SP3/SP4 + coverage manifest SE3/SE4 |

### 5.3 `repay`

Entry point: model `op.create_repayment_transaction(amount, officer, date)` or view `record_transaction_repayment` (`POST repayment/<pk>/create`).

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VRp1 | Amount > 0 | `amount > 0` | `ValidationError` | `"The amount should be more than 0"` | [`validate_repayement_amount`](../../apps/app_base/mixins.py:523) | [`test_zero_repayment_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:320) |
| VRp2 | Amount ≤ remaining | `amount <= amount_remaining_to_repay` | `ValidationError` | `"The paid amount %(amount)s exceeds the remaining: %(remaining)s"` | [`validate_repayement_amount`](../../apps/app_base/mixins.py:525) | [`test_repayment_exceeding_remaining_balance_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:299), [`test_partial_repayment_then_over_repayment_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:307) |
| VRp3 | Capped by disbursed amount | `amount <= repayable_amount == min(total, amount_settled)` | `ValidationError` | same as VRp2 | [`repayable_amount`](../../apps/app_base/mixins.py:480) | [`test_repayment_blocked_when_no_disbursement`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:218), [`test_amount_remaining_to_repay_reflects_disbursed_cap`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:242), [`test_repayment_cannot_exceed_total_disbursed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:254) |
| VRp4 | Closed-period guard on repayment date | governing period open on `date` | `ValidationError` | `"Cannot record a repayment dated within a closed financial period."` | [`create_repayment_transaction()`](../../apps/app_base/mixins.py:558) | covered by period suite |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SRp1 | `LOAN_REPAYMENT` created | `debtor.fund → creditor.fund`, type `LOAN_REPAYMENT` | [`create_repayment_transaction()`](../../apps/app_base/mixins.py:545) | [`test_repayment_creates_loan_repayment_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:110) |
| SRp2 | Repayment direction | `source=debtor`, `target=creditor` | repayment source/target funds | [`test_repayment_transaction_direction_is_debtor_to_creditor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:122) |
| SRp3 | Debtor fund ▼ amount | `debtor.balance` decreases by `amount` | `Entity.balance_at` | [`test_debtor_fund_decreases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:166) |
| SRp4 | Creditor fund ▲ amount | `creditor.balance` increases by `amount` | `Entity.balance_at` | [`test_creditor_fund_increases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:179) |
| SRp5 | Debtor payables ▼ | `debtor.payables` decreases by `amount` | payables derivation | [`test_repayment_decreases_debtor_payables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:196) |
| SRp6 | Creditor receivables ▼ | `creditor.receivables` decreases by `amount` | receivables derivation | [`test_repayment_decreases_creditor_receivables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:207) |
| SRp7 | `amount_remaining_to_repay` ▼ | remaining decreases by `amount` | `amount_remaining_to_repay` | [`test_amount_remaining_to_repay_decreases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:133) |
| SRp8 | Multiple repayments accumulate | remaining sums all active repayments | `amount_repayed` | [`test_multiple_repayments_accumulate`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:142) |
| SRp9 | Full repayment → `is_fully_repayed` | `amount_repayed == repayable_amount`, remaining `0` | `is_fully_repayed` | [`test_full_repayment_marks_as_fully_repayed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:156) |
| SRp10 | Differential invariant (repay + reverse) | repay then reverse the repayment returns to the advance-only state | whole engine | [`test_repay_then_reverse_repayment_returns_to_advance_state`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:281) |

### 5.4 Individual transaction reversal (pay / repay)

The **operation-level** reverse is distinct from reversing an individual `LOAN_PAYMENT` or `LOAN_REPAYMENT` transaction.

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| TR1 | Repayment tx reversed | `amount_repayed` ↓, `is_fully_repayed` unset, `amount_remaining_to_repay` restored; debtor ▲, creditor ▼; debtor payables ▲, creditor receivables ▲ | `Transaction.reverse()` | [`test_full_repayment_reversed_restores_remaining_balance`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:332), [`test_partial_repayment_reversed_restores_remaining_balance`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:352), [`test_only_reversed_repayment_is_net_out`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:372) |
| TR2 | Payment tx reversed | returns balance to creditor, decreases debtor; debtor payables ▼, creditor receivables ▼ | `Transaction.reverse()` | engine-level (shared) |
| TR3 | Asymmetric reversal allowed | reversing more payment txs than repayments is allowed — can introduce inconsistency (negative receivables/payables are permitted) | engine-level | documented behavior |

### 5.5 `reverse` (operation level)

Entry point: model `op.reverse(officer, date, reason)` or view `operation_reverse_view` (`POST <pk>/reverse/`).

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VR1 | Not already reversed | `reversed_by is None` | `ValidationError` | `"The transaction is already reversed."` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:34) | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:212) |
| VR2 | Not itself a reversal | `reversal_of is None` | `ValidationError` | `"You can't reverse this record as it is a reversal of …"` | [`ReversableModel._validate_can_be_reversed`](../../apps/app_base/models.py:171) + view guard [`reverse.py`](../../apps/app_operation/views/reverse.py:47) | [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:219) |
| VR3 | No non-reversed disbursements | no active `LOAN_PAYMENT` tx | `ValidationError` | `"You can't reverse this object as it has non-reversed transactions…"` | [`ReversableModel._requires_transaction_reversal`](../../apps/app_base/models.py:203) + `_reversable_transaction_types` ([`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:77)) | [`test_reversal_blocked_when_payment_disbursement_exists`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:162) |
| VR4 | No outstanding repayments | no active `LOAN_REPAYMENT` tx | `ValidationError` | same as VR3 | [`_requires_transaction_reversal()`](../../apps/app_operation/models/proxies/op_loan.py:99) | [`test_reversal_blocked_when_repayment_exists`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:172) |
| VR5 | Reason required | `POST['reversal_reason']` non-empty | view redirect + message | `"A reason for reversal is required."` | [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:84) | view contract (see §8) |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SR1 | Reversal record created | cloned op, `reversal_of = original` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:235) | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:77) |
| SR2 | Original marked reversed | `original.reversed_by = reversal` | [`ReversableModel.reverse()`](../../apps/app_base/models.py:270) | [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:83) |
| SR3 | Reversal is a reversal, not reversed | `reversal.is_reversal`, `not reversal.is_reversed` | [`ReversableModel`](../../apps/app_base/models.py:133) | [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:90) |
| SR4 | Reversal inherits identity | `amount`, `source`, `destination` copied | [`ReversableModel._get_reverse_kwargs`](../../apps/app_base/models.py:184) | [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:96) |
| SR5 | Counter-tx for issuance only | 1 × reversed `LOAN_ISSUANCE`; payments/repayments must be cleared manually | `_implicit_reversable_transaction_types` ([`op_loan.py`](../../apps/app_operation/models/proxies/op_loan.py:95)) | [`test_reverse_creates_counter_issuance_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:103) |
| SR6 | Counter-tx flips funds | `counter.source = original.target`, `counter.target = original.source`, same amount | [`Transaction.reverse()`](../../apps/app_transaction/models.py:206) | [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:111) |
| SR7 | Obligations remain zero | issuance reversal creates no payables/receivables | obligation derivation | [`test_reverse_issuance_leaves_obligations_zero`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:127) |
| SR8 | Differential invariant | create + reverse leaves the whole world unchanged (balances, payables, receivables, ledger) | whole engine | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:139) |

### 5.6 Immutability

`source`, `destination`, `amount` (and `period`) **cannot be changed after save** — enforced by [`ImmutableMixin`](../../apps/app_base/mixins.py:30) via `_immutable_fields` ([`operation.py`](../../apps/app_operation/models/operation.py:51)).

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `source` changed after save | `ImmutableMixin.save()` | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:261) |
| `destination` changed after save | `ImmutableMixin.save()` | [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:270) |
| `amount` changed after save | `ImmutableMixin.save()` | [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:279) |

---

## 6. Period & financial-period contract

- Every real (non-world/system) entity gets an **open** period on creation (start = creation date, `end_date=None`) — [`Entity.save()`](../../apps/app_entity/models/__init__.py:714).
- The operation's governing entity (`period_entity`) is the **source creditor** (`_source_role = "url"`) — [`Operation.period_entity`](../../apps/app_operation/models/operation.py:498).
- On create, `period` is auto-assigned to the covering period; if none covers the date, creation fails (VC11).
- New operations dated inside a **closed** period are rejected (VC10) — [`is_date_in_closed_period`](../../apps/app_operation/models/period.py:14).
- **Pay and repay** transactions are also rejected if dated inside a closed period of the governing entity (VP5, VRp4).
- Reversals are **exempt** from the closed-period and covering-period checks and may land in a different open period ([`_reverse_period`](../../apps/app_operation/models/operation.py:455)).

---

## 7. Entity roles & balance contract

- Both sides must be **non-virtual** Person or Project entities — enforced at model (VC1/VC2/VC15) and transaction (VC13 `not_virtual`/`not_virtual`) layers. **World and System can never participate** in a loan.
- `creditor.balance` / `debtor.balance` are derived exclusively from **payment-type** transactions (`LOAN_PAYMENT`, `LOAN_REPAYMENT`); the issuance tx (`LOAN_ISSUANCE`) never moves a balance.
- **Disbursement (`LOAN_PAYMENT`)** increases debtor payables and creditor receivables; **repayment (`LOAN_REPAYMENT`)** decreases them. The issuance itself creates no obligations.
- The creditor is a real payer, so each disbursement is **balance-checked** (VP1); the loan issuance itself is deliberately unguarded (VC12).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Create route | `POST/GET /<entity_pk>/loan/create` → [`OperationCreateView`](../../apps/app_operation/views/create_operation/base.py:75) |
| Source selection | locked to the URL entity — the **creditor** (`_source_role="url"`) |
| Destination selection | secondary-entity picker (`_dest_role="post"`) — Person/Project list excluding the URL entity, via [`get_related_entities`](../../apps/app_operation/models/proxies/op_loan.py:82) |
| Category | hidden (no category) |
| Amount | raw `amount` POST field ([`_compute_amount`](../../apps/app_operation/views/create_operation/base.py:52)); validated > 0 at model |
| POST parsing | [`OperationDataValidator`](../../apps/app_operation/validators.py:45) — date format, description, category (n/a) |
| List entry | "Debt Issuance" link in [`operation_list.html`](../../apps/app_operation/templates/app_operation/operation_list.html:18) |
| Detail | [`operation_detail_view`](../../apps/app_operation/views/detail.py:14) — shows issuance + disbursements + repayments, outstanding balance to pay and to repay, over-repayment indicator, Record Payment / Record Repayment / Reverse buttons |
| Pay | `payment/<pk>/create` → [`record_transaction_payment`](../../apps/app_operation/views/record_transaction.py:17) — `PaymentForm`, balance enforced (VP1), shows `amount_remaining_to_settle` |
| Repay | `repayment/<pk>/create` → [`record_transaction_repayment`](../../apps/app_operation/views/record_transaction.py:137) — `PaymentForm`, `can_repay` guard, shows `amount_remaining_to_repay`, blocks over-repayment |
| Reverse | `/<pk>/reverse/` → [`operation_reverse_view`](../../apps/app_operation/views/reverse.py:13) — `POST` requires `reversal_reason`; guards already-reversed / is-reversal (VR1/VR2) |

---

## 9. Branch catalog (all possible branches)

**create — validation:** VC1 source person|project · VC2 dest person|project · VC3 source active · VC4 dest active · VC5 source fund active · VC6 target fund active · VC7 amount>0 · VC8 officer staff · VC9 officer active · VC10 not closed-period · VC11 covering period exists · VC12 balance exempt at create · VC13 tx entity-type (non-virtual both) · VC14 tx op-type (Loan) · VC15 source≠dest

**create — effects:** SC1 issuance tx · SC2 direction creditor→debtor · SC3 amount matches · SC4 no payment at save · SC5 no balance effect · SC6 not repayable pre-disbursement · SC7 creditor/debtor aliases · SC8 person|project either side

**pay — validation:** VP1 balance per disbursement · VP2 amount>0 · VP3 amount≤remaining · VP4 partial allowed · VP5 not closed-period

**pay — effects:** SP1 `LOAN_PAYMENT` created · SP2 direction creditor→debtor · SP3 creditor ▼ · SP4 debtor ▲ · SP5 debtor payables ▲ · SP6 creditor receivables ▲ · SP7 other buckets zero · SP8 amount_settled ↑

**repay — validation:** VRp1 amount>0 · VRp2 amount≤remaining · VRp3 capped by disbursed · VRp4 not closed-period

**repay — effects:** SRp1 `LOAN_REPAYMENT` created · SRp2 direction debtor→creditor · SRp3 debtor ▼ · SRp4 creditor ▲ · SRp5 debtor payables ▼ · SRp6 creditor receivables ▼ · SRp7 remaining ▼ · SRp8 multiple accumulate · SRp9 full → fully repayed · SRp10 differential invariant

**reverse — validation:** VR1 not reversed · VR2 not a reversal · VR3 no disbursements · VR4 no outstanding repayments · VR5 reason required (view)

**reverse — effects:** SR1 reversal record · SR2 original reversed · SR3 is reversal · SR4 identity copied · SR5 issuance counter-tx only · SR6 funds flipped · SR7 obligations zero · SR8 differential invariant

**tx reversal / immutability:** TR1 repayment reversed → repaid state restored · TR2 payment reversed · TR3 asymmetric reversal allowed · IM1/IM2/IM3 source/destination/amount immutable

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| Issuance tx | [`test_creates_issuance_transaction_on_save`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:85) | SC1, SC4 |
| Issuance direction | [`test_issuance_transaction_direction_is_creditor_to_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:92) | SC2 |
| Issuance amount | [`test_issuance_transaction_amount_matches_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:100) | SC3 |
| Repay cap pre-disbursement | [`test_amount_remaining_to_repay_is_zero_without_disbursement`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:107) | SC6, VC12 |
| Aliases | [`test_creditor_property`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:118), [`test_debtor_property`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:124) | SC7 |
| Side combinations | [`test_project_as_creditor_person_as_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:130), [`test_source_can_be_person_or_project`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:175), [`test_source_vendor_person_is_still_a_valid_creditor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:184) | SC8 |
| Active entities | [`test_source_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:143), [`test_source_fund_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:151), [`test_destination_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:163) | VC3–VC6 |
| Side type exclusion | [`test_source_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:198), [`test_source_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:192), [`test_destination_world_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:203), [`test_destination_system_entity_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:208) | VC1, VC2 |
| Distinctness | [`test_source_and_destination_must_be_different`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:218) | VC15 |
| Amount | [`test_amount_zero_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:227), [`test_amount_negative_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:232) | VC7 |
| Officer | [`test_officer_user_must_be_staff`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:241), [`test_officer_must_be_active`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:249) | VC8, VC9 |
| Immutability | [`test_source_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:261), [`test_destination_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:270), [`test_amount_is_immutable`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:279) | IM1–IM3 |
| Balance check flag | [`test_check_balance_on_payment_is_enabled`](../../apps/app_operation/tests/operations/loan/test_loan_loan_create.py:291) | VC12, VP1 |
| Payment tx | [`test_payment_creates_loan_payment_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:75) | SP1 |
| Payment direction | [`test_payment_transaction_direction_is_creditor_to_debtor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:87) | SP2 |
| Creditor ▼ | [`test_creditor_fund_decreases_after_payment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:98) | SP3 |
| Debtor ▲ | [`test_debtor_fund_increases_after_payment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:111) | SP4 |
| Multiple disbursements | [`test_multiple_payment_disbursements_allowed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:124) | VP4 |
| Payables ▲ | [`test_payment_increases_debtor_payables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:145) | SP5 |
| Receivables ▲ | [`test_payment_increases_creditor_receivables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:155) | SP6 |
| Other buckets zero | [`test_payment_leaves_other_obligation_buckets_zero`](../../apps/app_operation/tests/operations/loan/test_loan_loan_disbursement.py:165) | SP7 |
| Repayment tx | [`test_repayment_creates_loan_repayment_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:110) | SRp1 |
| Repayment direction | [`test_repayment_transaction_direction_is_debtor_to_creditor`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:122) | SRp2 |
| Remaining ▼ | [`test_amount_remaining_to_repay_decreases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:133) | SRp7 |
| Multiple repayments | [`test_multiple_repayments_accumulate`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:142) | SRp8 |
| Full repayment | [`test_full_repayment_marks_as_fully_repayed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:156) | SRp9 |
| Debtor ▼ | [`test_debtor_fund_decreases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:166) | SRp3 |
| Creditor ▲ | [`test_creditor_fund_increases_after_repayment`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:179) | SRp4 |
| Payables ▼ | [`test_repayment_decreases_debtor_payables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:196) | SRp5 |
| Receivables ▼ | [`test_repayment_decreases_creditor_receivables`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:207) | SRp6 |
| No-disbursement block | [`test_repayment_blocked_when_no_disbursement`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:218) | VRp3, SC6 |
| Disbursed cap | [`test_amount_remaining_to_repay_reflects_disbursed_cap`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:242), [`test_repayment_cannot_exceed_total_disbursed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:254) | VRp3 |
| Over-repayment | [`test_repayment_exceeding_remaining_balance_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:299), [`test_partial_repayment_then_over_repayment_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:307), [`test_zero_repayment_raises_validation_error`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:320) | VRp2, VRp1 |
| Repay differential | [`test_repay_then_reverse_repayment_returns_to_advance_state`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:281) | SRp10, TR1 |
| Repayment reversal restores state | [`test_full_repayment_reversed_restores_remaining_balance`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:332), [`test_partial_repayment_reversed_restores_remaining_balance`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:352), [`test_only_reversed_repayment_is_net_out`](../../apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:372) | TR1 |
| Reverse happy path | [`test_reverse_creates_reversal_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:77), [`test_reverse_marks_original_as_reversed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:83), [`test_reversal_is_reversal`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:90), [`test_reverse_inherits_amount_source_destination`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:96) | SR1–SR4 |
| Counter-tx | [`test_reverse_creates_counter_issuance_transaction`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:103), [`test_reverse_counter_transaction_flips_funds`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:111) | SR5, SR6 |
| Obligations zero | [`test_reverse_issuance_leaves_obligations_zero`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:127) | SR7 |
| Reverse differential | [`test_create_then_reverse_leaves_world_unchanged`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:139) | SR8 |
| Reverse blocked by disbursement | [`test_reversal_blocked_when_payment_disbursement_exists`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:162) | VR3 |
| Reverse blocked by repayment | [`test_reversal_blocked_when_repayment_exists`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:172), [`test_reversal_still_blocked_after_repayment_reversed`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:189) | VR4 |
| Reverse constraints | [`test_cannot_reverse_already_reversed_operation`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:212), [`test_cannot_reverse_a_reversal`](../../apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:219) | VR1, VR2 |

---

## 11. Tasks

- [x] Verify issuance transaction created correctly (creditor → debtor, type `LOAN_ISSUANCE`)
- [x] Verify both entities must be `active=True`
- [x] Verify source fund must be `active=True`
- [x] Verify amount/officer validations (zero, negative, non-staff, inactive, no-user)
- [x] Verify immutability of `source`, `destination`, `amount` after save
- [x] Verify repayment view creates transaction in correct direction: `destination.fund → source.fund` (debtor → creditor)
- [x] Verify repayment transaction type is `LOAN_REPAYMENT`
- [x] Verify `amount_remaining_to_repay` property: capped by the disbursed amount
  (`min(issuance_amount, sum(LOAN_PAYMENT)) - sum(repayments)`)
- [x] Verify repayment cannot exceed remaining balance (`amount_remaining_to_repay`)
- [x] Verify repayment is blocked when no disbursement (`LOAN_PAYMENT`) exists
- [x] Verify repayment cannot exceed the total disbursed amount (payment sum)
- [x] Verify creditor fund decreases after payment disbursement
- [x] Verify debtor fund increases after payment disbursement
- [x] Verify multiple payment disbursements allowed
- [x] Verify debtor fund decreases after repayment
- [x] Verify creditor fund increases after repayment
- [x] Verify multiple repayments accumulate correctly
- [x] Verify full repayment marks as fully repayed
- [x] Reversal: only issuance counter-transaction is created (payment disbursements block reversal)
- [x] Verify reversal blocked when payment disbursements exist
- [x] Verify reversal blocked if outstanding repayments exist (debtor → creditor LOAN_REPAYMENT transactions)
- [x] Verify reversal marks original as reversed and sets `reversed_by`
- [x] Verify cannot reverse an already-reversed operation
- [x] Verify cannot reverse a reversal operation
- [ ] UI: create form works; detail shows outstanding balance and "Record Repayment" button
- [ ] UI: repayment button shows remaining balance, blocks over-repayment
- [ ] Add a focused test for the payment **balance-insufficient** branch (VP1 failure outcome)
- [ ] Add a focused test for the operation **closed-period** create guard (VC10/VC11) specific to Loan
