# EPIC 5 — Entity & Stakeholder Management

> **Design note — Entities as mutual vendor/client**
> An entity (person or project) can simultaneously act as a **vendor** to one party and a **client** of another.
> The `Stakeholder` model captures this at the relationship level (`parent` ↔ `target` with a `role`),
> while the `Entity.is_vendor` / `Entity.is_client` flags are convenience denormalisations for global filtering.
> Example: *Project A* can be a vendor to *Project B* (supplying goods) while also being a client of *Project C* (purchasing services).
> There is no constraint preventing an entity from holding both roles across different stakeholder records, or even within the same parent if the business relationship warrants it.

---

### Feature 5.1 — Entity List Filtering
**Goal:** The entity list shows all entities, but users need to filter by type (person / project / vendor / client / worker).

Tasks:
- [ ] Add query param filtering in `entity_list.py` view: `?type=person`, `?type=project`, etc.
- [ ] Update `entity_list.html` filter buttons to pass the correct param
- [ ] Ensure the active filter is visually highlighted

---

### Feature 5.2 — Stakeholder Active/Inactive Toggle
**Goal:** Stakeholders have an `active` field but there's no UI to deactivate one.

Tasks:
- [ ] Add a toggle-active view for stakeholders
- [ ] Show active/inactive status on stakeholder list in entity detail
- [ ] Inactive workers should not appear in the WorkerAdvance destination dropdown

---

### Feature 5.3 — Contact Info Completeness
**Goal:** Contact info forms exist but the display in entity detail may be incomplete.

Tasks:
- [ ] Audit `entity_detail.html` — confirm contact info tab renders all `ContactInfo` types (phone, email, address, website)
- [ ] Add primary contact highlight (bold/badge for `is_primary=True`)
- [ ] Add "set as primary" action
