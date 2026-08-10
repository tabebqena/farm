All Opertaions:
Operations (19 total)
Fund / Capital
#	OperationType	Label	Proxy class	Spec
1	CASH_INJECTION	Cash Injection	CashInjectionOperation	op_1_cash_injection.md
2	CASH_WITHDRAWAL	Cash Withdrawal	CashWithdrawalOperation	op_2_cash_withdrawal.md
3	PROJECT_FUNDING	Project Funding	ProjectFundingOperation	op_3_project_funding.md
4	PROJECT_REFUND	Project Refund	ProjectRefundOperation	op_4_project_refund.md
5	CAPITAL_GAIN	Capital Gain	CapitalGainOperation	op_5_capital_gain.md
6	CAPITAL_LOSS	Capital Loss	CapitalLossOperation	op_6_capital_loss.md

Movement & Transfer 
#	OperationType	Label	Proxy class	Spec
7	INTERNAL_TRANSFER	Internal Transfer	InternalTransferOperation	op_7_internal_transfer.md
8	LOAN	Loan	LoanOperation	op_8_loan.md

Distribution & Adjustments
#	OperationType	Label	Proxy class	Spec
9	PROFIT_DISTRIBUTION	Profit Distribution	ProfitDistributionOperation	op_9_profit_distribution.md
10	LOSS_COVERAGE	Loss Coverage	LossCoverageOperation	op_10_loss_coverage.md
11	WORKER_ADVANCE	Worker Advance	WorkerAdvanceOperation	op_11_worker_advance.md
12	EXPENSE	Expense	ExpenseOperation	op_12_expense.md
13	PURCHASE	Purchase	PurchaseOperation	op_13_purchase.md
14	SALE	Sale	SaleOperation	op_14_sale.md

15	CORRECTION_CREDIT	Correction Credit	CorrectionCreditOperation	op_15_correction.md
16	CORRECTION_DEBIT	Correction Debit	CorrectionDebitOperation	op_15_correction.md

Inventory / Livestock (not in operations specs)
#	OperationType	Label	Proxy class
17	BIRTH	Birth	BirthOperation
18	DEATH	Death	DeathOperation
19	CONSUMPTION	Consumption	ConsumptionOperation


# Eagle Eye review (done by ai chat):

- Cash Injection (Validation & effect ) passed.
- Cash Withdrawal ( Validation & effect ) passed.
- Project Funding (Validation & effect ) passed.
- Project Funding ( Validation & effect ) passed.
- Capital Gain ( Validation & effect ) passed.
- Capital Loss ( Validation & effect ) passed.

- CORRECTION_CREDIT ( Validation & effect ) passed.
- CORRECTION_DEBIT ( Validation & effect ) passed.
- INTERNAL_TRANSFER ( Validation & effect ) passed.
- LOAN ( Validation & effect ) passed.
- Birth ( Validation & effect ) passed.
- DEATH ( Validation & effect ) passed (has gaps).
- CONSUMPTION ( Validation & effect ) passed (has gaps).
- Expense ( Validation & effect ) passed (has gaps).

- Purchase passed.
- Sale passed.
- PROFIT_DISTRIBUTION passed.
- LOSS_COVERAGE passed.


N.B:. Observation / Gap
There are no dedicated BIRTH operation tests under apps/app_operation/tests/operations/ (no birth/ directory — unlike cash, capital, purchase, etc.). BIRTH is only exercised indirectly by inventory tests such as test_record_birth(). So the "Validation & effect" review for BIRTH currently rests on those inventory tests plus manual analysis; an end-to-end creation/reversal test suite (like test_cash_injection_cash_injection_create.py) does not yet exist fo

Death:
No clean_source on DeathOperation (a Project-source check exists on ConsumptionOperation but not here).
No dedicated DEATH tests under apps/app_operation/tests/operations/ (a search returned zero results) — same gap flagged for BIRTH in Review.md. DEATH is currently exercised only indirectly via inventory tests like test_record_death() and test_status_dead_after_death().
No specs/operations/op_18_death.md — DEATH validation/effects are not documented anywhere.

Consumption:
No movement lines are auto-created for CONSUMPTION. _auto_create_inventory_movements() only runs for BIRTH and DEATH. Yet:
Operation.reverse() puts CONSUMPTION in the "BIRTH, DEATH, CONSUMPTION" group that assumes auto-created movement lines and reverses them.
The stock detail "consumed" tab filters on CONSUMPTION movement lines (views.py), so consumed products likely never appear there via the normal creation path.
The ledger therefore gets only the issuance entry, never a CONSUMPTION_MOVEMENT entry — even though that entry type exists in record_movement_line().
No op_19_consumption.md spec — CONSUMPTION is in the "Inventory / Livestock (not in operations specs)" bucket in Review.md.
No dedicated tests — there is no tests/operations/consumption/ (or birth/death) directory; the only CONSUMPTION coverage is indirect inventory tests like test_record_consumption-style ledger tests under test_product_ledger_entry.py.


Consolidated comparison:
- A cross-operation reference document now exists at specs/operations/operations-comparison.md — it consolidates the "Validation & effect" review for all 19 operations into (1) a validation comparison matrix (ENFORCE / EXEMPT / N/A per check) and (2) a success-effects matrix (which operation affects which outcome), plus the gap notes below.

Expense:

Category required — class-level has_category=True, category_required=True, category_type="EXPENSE" (op_expense.py). Currently enforced at the view/validator layer only: OperationDataValidator._parse_category() rejects a missing/invalid category, and the dropdown is filtered to active EXPENSE categories in base.py:_build_context(). ⚠️ The model-save-level FK enforcement is still a pending task (spec line 62 of op_12_expense.md).