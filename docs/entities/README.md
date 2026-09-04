# Entities

> **Entity contracts:** The `app_entity` domain is documented as a set of
> **primary-source contracts** that mirror the operation contracts under
> `docs/operations/` (see [`_OPERATION_SPEC_TEMPLATE.md`](../operations/_OPERATION_SPEC_TEMPLATE.md)).
> Where the operation specs pin the money-moving "what happens", the entity
> specs pin the "who" and the structural scaffolding every operation consumes —
> Entity types & lifecycle, Person, Project & the setup wizard, Stakeholder
> relationships, ContactInfo, and FinancialCategory. Each contract records all
> possible branches, registers every implementing file (models, base machinery,
> views, templates) plus the tests that pin each branch. Where code and spec
> disagree, the spec is authoritative — fix the code, not the spec. The shared
> structure is defined in [`_ENTITY_SPEC_TEMPLATE.md`](_ENTITY_SPEC_TEMPLATE.md);
> **Entity lifecycle ([entity_1](entity_1_lifecycle.md)) is the foundation** the
> other areas build on. Remaining areas are registered under the same structure.

## Foundation
- [Entity 1: Entity Lifecycle & Types](entity_1_lifecycle.md)

## Parties
- [Entity 2: Person](entity_2_person.md)
- [Entity 3: Project & Setup Wizard](entity_3_project.md)

## Relationships & Structure
- [Entity 4: Stakeholder](entity_4_stakeholder.md)
- [Entity 5: Contact Info](entity_5_contact_info.md)
- [Entity 6: Financial Categories](entity_6_financial_categories.md)
