# Financial Period
**App:** `app_operation`
**Model:** `FinancialPeriod`
**Concept:** Tracks open/closed accounting periods per entity. Each operation is assigned to the entity's open period at creation time. Periods can be closed (setting an `end_date`), which automatically opens a new period for active entities.

---

## Model fields

| Field        | Type            | Notes                                              |
|--------------|-----------------|----------------------------------------------------|
| `entity`     | FK → Entity     | Immutable after save                               |
| `start_date` | DateField       | Immutable after save; auto-set to entity creation date for first period, or to the close date of the previous period |
| `end_date`   | DateField       | Null = open. Set via `close(end_date)`. Immutable once set. |

**Computed:**
- `is_closed`: `end_date is not None and end_date < today`

**Auto-creation:** A `FinancialPeriod` is automatically created via a post-save signal when a Person or Project entity is created. World and System entities do not get periods.

**Operation assignment:** Operations are auto-assigned to the destination entity's open period at creation. Reversals are exempt (can be recorded even in/after a closed period).

---

## Validation

- `start_date` is immutable after save
- `entity` is immutable after save
- `end_date` is immutable once set (cannot change a closed period's end date)
- `close(end_date)` raises if `end_date < start_date`
- `close(end_date)` raises if the period is already closed
- Only one open period (no `end_date`) per entity at a time
- Periods for the same entity must not overlap (`start_date`/`end_date` ranges)
- Non-overlapping sequential periods for the same entity are allowed

---

## Tasks

**Auto-creation**
- [x] New Person entity gets a FinancialPeriod automatically
- [x] New Project entity gets a FinancialPeriod automatically
- [x] World entity does not get a period
- [x] System entity does not get a period
- [x] Auto-created period is open (no end_date)
- [x] Auto-created period start_date matches entity creation date

**Closing**
- [x] `close(end_date)` sets the end_date on the period
- [x] `close(end_date)` with end_date before start_date raises
- [x] Closing an already-closed period raises
- [x] `close(end_date)` returns a new open period for active entities
- [x] `close(end_date)` returns None for inactive entities
- [x] New period start_date equals the close date

**Immutability**
- [x] `end_date` is immutable once set
- [x] `start_date` is immutable after save
- [x] `entity` is immutable after save

**Overlap / uniqueness constraints**
- [x] Overlapping period for the same entity raises
- [x] Two open periods for the same entity raises
- [x] Non-overlapping sequential periods for the same entity are allowed
- [x] Same date range for different entities does not raise

**is_closed logic**
- [x] `is_closed` is False when end_date is today
- [x] `is_closed` is True when end_date is yesterday
- [x] `is_closed` is False when end_date is tomorrow

**Operation assignment**
- [x] Operations get a period auto-assigned at creation
- [x] Assigned period is the entity's open period
- [x] After closing a period, new operations are assigned to the newly opened period
- [x] Operations in a closed period raise ValidationError
- [x] Operations with a date before any period raise (no applicable period)
- [x] Operations raise when no open period exists
- [x] Operations with a future end_date are allowed (end_date not yet past)
- [x] Reversals are not blocked by a closed period

**Period entity**
- [x] The period entity is the destination entity for cash-injection-style operations

**UI**
- [ ] Period list per entity (showing open/closed status, dates)
- [ ] Close period form (choose end_date, previews what new period will open)
- [ ] Warning on operation create if entity has no open period
