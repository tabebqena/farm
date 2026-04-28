# EPIC 2 — Operation Bugs & Missing Flows

---

### Feature 2.1 — Fix AppConfig Names
**Goal:** Apps won't load correctly due to wrong `AppConfig.name` values.

Tasks:
- [x] Fix `apps/app_adjustment/apps.py`: change `name = "app_adjustment"` → `name = "apps.app_adjustment"`
- [x] Fix `apps/app_evaluation/apps.py`: same pattern
- [x] Verify all other `apps.py` files follow the `apps.<app_name>` convention
- [x] Run `python manage.py check` — should report 0 errors

---

### Feature 2.2 — Reversal Alert Template Bug
**Goal:** `reversal_alert.html` has two conditions both checking `operation.is_reversed`. Second should be `is_reversal`.

Tasks:
- [x] Fix line 12 in `reversal_alert.html`: `elif operation.is_reversed` → `elif operation.is_reversal`
- [ ] Manually test: open a reversed operation and a reversal operation — both should show the correct badge

---

### Feature 2.3 — Worker Advance Repayment Flow
**Goal:** `WorkerAdvanceOperation` declares `_repayment_transaction_type` but the repayment recording view doesn't handle it yet. The advance repayment button shows in the UI but likely fails.

Tasks:
- [ ] Trace `record_transaction.py` view — confirm it handles `WORKER_ADVANCE_REPAYMENT` type
- [ ] If missing: add a branch in `record_transaction.py` for repayment transaction creation
- [ ] Test: create a worker advance → record a repayment → balance should decrease

---

### Feature 2.4 — Operation List Entity Typo
**Goal:** `entity_detail.html` has `entity.perosn` (typo) causing silent template errors.

Tasks:
- [x] Fix `entity.perosn` → `entity.person` in `entity_detail.html`
- [x] Search the entire templates directory for other typos: `grep -r "perosn\|entiy\|opertion" templates/`
