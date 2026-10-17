# Plan: action provenance / "What happened & why" tracing

## Goal

When the app auto-creates rows under the hood (transactions, inventory
movements, financial periods, valuations, lazy products, reversals), a user
facing an unexpected or wrong entry must be able to see **what** the app did and
**why**, and judge whether the mistake was theirs or the app's — instead of
blindly soft-deleting and re-entering.

## Decisions

- **Storage:** DB (queryable, shown in the UI).
- **Consistency:** audit writes happen in the same DB transaction as the change.
- **Granularity:** record *every* `BaseModel.save()`, storing the row's full
  **new shape** (post-save values).
- **Display levels:** 1) USERINPUT, 2) Auto-created rows + why, 3) Every save.
- **Audience:** all officers. **Scope:** everything.
- **Purge:** CLI command.
- Prior snapshot/export-import work: moved to branch `feature/data-export-import`
  for later revision.

## Design

- New `apps/app_audit` app with two append-only models:
  - `ActionTrace` — one per mutating request (actor, method/path, sanitized
    payload, status, error, root record, duration).
  - `SaveLog` — one per save (record ref, kind, `new_shape`, and for derived rows
    `is_derived` / `role` / `reason_code` / `reason_text`).
  - Both are plain `models.Model` (infrastructure: not soft-deleted, not
    self-tracked, hard-purgeable).
- `context.py` request-scoped runtime (contextvars) + `record_save` hook called
  from `BaseModel.save()`; `derived(role, reason)` tags auto-created rows.
- `middleware.py` opens/closes the trace per mutating request; the trace row is
  committed independently so failures are recorded even when the view's
  `transaction.atomic()` rolls back; final status written after the block exits.
- `reasons.py` catalog of plain-language explanations, cross-referenced by the
  operation specs under `docs/`.
- UI: `/audit/` Activity, `/audit/trace/<id>/` (three levels), and
  `/audit/record/<app>/<model>/<id>/`; "History / Why?" links on operation,
  entity and product detail pages.
- `manage.py purge_savelogs` to trim the trail.

## Implemented

- `apps/app_audit/`: `models.py`, `serialization.py`, `reasons.py`,
  `context.py`, `middleware.py`, `admin.py` (read-only), `views.py`, `urls.py`,
  `templatetags/audit_tags.py`, `management/commands/purge_savelogs.py`,
  templates (`activity.html`, `trace_detail.html`, `record_history.html`),
  migration `0001_initial.py`, and tests.
- Settings: `apps.app_audit` in `INSTALLED_APPS`; `ActionTraceMiddleware` in
  `MIDDLEWARE`; `FARM_TRACKING_ENABLED` (default `True`, forced off under
  `manage.py test`). `farm/urls.py` mounts `/audit/`.
- `apps/app_base/models.py`: `BaseModel.save()` records each write;
  `_perform_soft_delete()` logs the tombstone with `provenance_kind`.
- `provenance.derived(...)` markers on: issuance / payment / repayment
  transactions (`app_base/mixins.py`); birth / death / consumption movements and
  capital valuations (`app_operation`); lazy products (`app_inventory`); entity
  period create/close (`app_entity`); reversals (`app_base`, `app_transaction`).
- `navigation.py`: Activity / Action Trace / Record History entries.
- Tests: `apps/app_audit/tests/` (serialization, save recording, derived tags,
  soft-delete kind, middleware, views, template tag, domain integration, purge
  command). Full suite green; `manage.py check` clean.
- `VERSION` 1.2.16 → 1.3.0 and a `CHANGES.md` entry.

## Notes / follow-ups

- Retention is manual (`purge_savelogs`); consider a scheduled purge if volume
  grows.
- The "auto-created" reason text is denormalised onto `SaveLog` at write time so
  the UI does not depend on the catalog outliving the producing code path.
- Snapshot export/import + app-wide `uid` remain on `feature/data-export-import`
  for possible future revision.
