# Model Relationships Diagram

```mermaid
erDiagram
    %% ====================
    %% app_base – Abstract / Foundation
    %% ====================
    BaseModel {
        datetime created_at
        datetime updated_at
        datetime deleted_at
        bool     deletable
    }
    ReversableModel {
        FK reversal_of "OneToOne → self"
        PK reversed_by  "Reverse relation"
    }

    BaseModel ||--o| ReversableModel : "extends (abstract)"

    %% ====================
    %% app_entity – Entities (People, Projects, System, World)
    %% ====================
    Entity {
        string entity_type  "PERSON | PROJECT | SYSTEM | WORLD"
        string name
        bool   is_vendor
        bool   is_client
        bool   is_worker
        bool   is_shareholder
        bool   active
    }
    ContactInfo {
        string contact_type  "phone | email | address | website"
        string value
        string label
        bool   is_primary
    }
    Stakeholder {
        FK    parent  "→ Entity"
        FK    target  "→ Entity"
        string role    "worker | client | vendor | shareholder"
    }
    FinancialPeriod {
        FK     entity     "→ Entity"
        date   start_date
        date   end_date
    }

    Entity ||--o{ ContactInfo       : "has"
    Entity ||--o{ Stakeholder       : "parent of"
    Entity ||--o{ Stakeholder       : "target of"
    Entity ||--o{ FinancialPeriod    : "has periods"
    Entity ||--o{ Operation         : "is source of"
    Entity ||--o{ Operation         : "is destination of"
    Entity ||--o{ Transaction       : "is source of"
    Entity ||--o{ Transaction       : "is target of"
    Entity ||--o{ Product           : "owns"
    Entity ||--o{ ProductTemplate   : "uses (M2M)"

    %% ====================
    %% app_operation – Operations (financial events)
    %% ====================
    Operation {
        FK    source          "→ Entity"
        FK    destination     "→ Entity"
        decimal amount
        string operation_type "19 types: PURCHASE, SALE, BIRTH, etc."
        date   date
        FK    officer         "→ User"
        FK    period          "→ FinancialPeriod"
        FK    plan            "→ FinancialPeriod"
        FK    reversal_of     "→ Operation (self-ref)"
        PK    reversed_by     "Reverse relation"
    }
    OperationType {
        string choices "PURCHASE | SALE | BIRTH | DEATH | EXPENSE | LOAN | etc."
    }
    InvoiceItem {
        FK    operation      "→ Operation"
        FK    product        "→ ProductTemplate"
        decimal quantity
        decimal unit_price
    }

    Operation ||--o{ InvoiceItem         : "has items"
    Operation ||--o{ Adjustment          : "has adjustments"
    Operation ||--o{ InvoiceItemAdjustment : "has item adjustments"
    Operation ||--o{ InventoryMovementLine : "has movements"
    ReversableModel ||--|| Operation     : "extends (via Operation)"

    %% ====================
    %% app_inventory – Inventory / Products
    %% ====================
    ProductTemplate {
        string name
        string nature   "ANIMAL | FEED | MEDICINE | PRODUCT"
        string tracking_mode "INDIVIDUAL | BATCH | COMMODITY"
        M2M   entities "→ Entity"
    }
    Product {
        FK    entity          "→ Entity"
        FK    product_template "→ ProductTemplate"
        M2M   invoice_items   "→ InvoiceItem"
        decimal quantity
        decimal unit_price
        string unique_id
        string status         "ACTIVE | SOLD | DEAD"
    }
    InventoryMovementLine {
        FK    operation      "→ Operation"
        FK    invoice_item   "→ InvoiceItem"
        decimal quantity
        date   date
        FK    reversal_of    "→ self"
        string group_key
    }
    ProductLedgerEntry {
        FK    product        "→ Product"
        string entry_type    "PURCHASE | SALE | BIRTH | DEATH | etc."
        date   date
        decimal quantity_delta
        decimal value_delta
        string idempotency_key "UNIQUE"
    }

    ProductTemplate ||--o{ Product            : "defines"
    ProductTemplate ||--o{ InvoiceItem        : "referenced in"
    Product          ||--o{ ProductLedgerEntry : "has ledger"
    InvoiceItem      ||--o{ InventoryMovementLine : "has movements"
    InvoiceItem      ||--o{ InventoryMovementLine : "is reversed by"
    InvoiceItem      ||--o{ Product           : "links to (M2M)"

    %% ====================
    %% app_transaction – Financial Transactions (Double-Entry)
    %% ====================
    Transaction {
        FK    source       "→ Entity"
        FK    target       "→ Entity"
        string type        "48 types: *_ISSUANCE / *_PAYMENT pairs"
        decimal amount
        FK    content_type "→ ContentType (GenericFK)"
        int    object_id   "→ document PK (GenericFK)"
        FK    reversal_of  "→ Transaction (self-ref)"
        PK    reversed_by  "Reverse relation"
        FK    officer      "→ User"
    }
    TransactionType {
        string choices "PURCHASE_ISSUANCE | PURCHASE_PAYMENT | SALE_ISSUANCE | etc."
    }

    Transaction ||--o| Transaction : "reversal_of (self-ref)"
    Transaction }o--|| Entity      : "source"
    Transaction }o--|| Entity      : "target"
    Transaction }o--|| Operation   : "document (GenericFK)"
    Transaction }o--|| Adjustment  : "document (GenericFK)"

    %% ====================
    %% app_adjustment – Corrections
    %% ====================
    Adjustment {
        FK    operation   "→ Operation"
        string type       "PUR_RET | SALE_DISC | etc."
        decimal amount
        date   date
        FK    officer     "→ User"
        FK    reversal_of "→ self"
    }
    InvoiceItemAdjustment {
        FK    operation   "→ Operation"
        string type       "PURCHASE_ITEM_INCREASE | etc."
        FK    adjustment  "→ Adjustment (OneToOne, set on finalize)"
        date   date
        FK    officer     "→ User"
        FK    reversal_of "→ self"
    }
    InvoiceItemAdjustmentLine {
        FK    adjustment      "→ InvoiceItemAdjustment"
        FK    invoice_item    "→ InvoiceItem"
        decimal new_quantity
        decimal new_unit_price
        bool   is_removed
    }

    Adjustment ||--|| ReversableModel      : "extends"
    InvoiceItemAdjustment ||--|| ReversableModel : "extends"
    Adjustment ||--o| Adjustment           : "reversal_of (self-ref)"
    Adjustment }o--|| Operation            : "belongs to"
    InvoiceItemAdjustment }o--|| Operation : "belongs to"
    InvoiceItemAdjustment ||--o| Adjustment : "finalize() → creates"
    InvoiceItemAdjustment ||--o{ InvoiceItemAdjustmentLine : "has lines"
    InvoiceItemAdjustmentLine }o--|| InvoiceItem : "adjusts"
```

## Simplified Conceptual Flow

```
                    ┌──────────────────────────────────────┐
                    │           ENTITY (app_entity)         │
                    │  Person / Project / System / World    │
                    └──────┬────────────┬──────────┬───────┘
                           │            │          │
              source/dest  │    owns    │   has    │
                           ▼            ▼          ▼
              ┌──────────────────┐  ┌──────┐  ┌─────────┐
              │    OPERATION     │  │PRODUCT│  │FINANCIAL│
              │ (app_operation)  │  │      │  │ PERIOD  │
              │ PURCHASE / SALE  │  │      │  │         │
              │ BIRTH / DEATH... │  │      │  │         │
              └───┬────┬────┬───┘  └──────┘  └─────────┘
                  │    │    │
         ┌────────┘    │    └──────────┐
         ▼             ▼               ▼
   ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │TRANSACTION│ │ADJUSTMENT│ │INVENTORY     │
   │(app_tx)  │ │          │ │MOVEMENT_LINE │
   │Double-   │ │PUR_RET   │ │              │
   │Entry     │ │SALE_DISC │ │              │
   │Cash Flow │ │etc.      │ │              │
   └──────────┘ └──────────┘ └──────────────┘
        │                           │
        │                           ▼
        │                   ┌────────────────┐
        │                   │PRODUCT_LEDGER  │
        │                   │_ENTRY          │
        │                   │(Append-only)   │
        │                   └────────────────┘
        │
        ▼
   ┌──────────┐
   │INVOICE   │
   │ITEM_ADJ  │── Creates ──▶ ADJUSTMENT (after finalize)
   │          │
   └──────────┘
        │
        ▼
   ┌──────────────┐
   │INVOICE_ITEM  │
   │_ADJ_LINE     │── Writes ──▶ ProductLedgerEntry
   └──────────────┘
```

## Reversal Pattern

All reversable models use the same self-referencing pattern:

```
Original Record ──(reversed_by)──▶ Reversal Record
Reversal Record ──(reversal_of)──▶ Original Record
```

Applied to: `Operation`, `Adjustment`, `InvoiceItemAdjustment`, `Transaction`, `InventoryMovementLine`

## Transaction Lifecycle Pattern

Each operation can generate 0-2 transaction types:

```
Operation.save()
  ├── create_issuance_transaction()  ──▶  *_ISSUANCE  (memo/obligation, no cash movement)
  └── create_payment_transaction()   ──▶  *_PAYMENT   (cash movement, for one-shot ops only)
```

## Key Design Decisions

1. **BaseModel** provides soft-delete, timestamps, deletable flag for all models
2. **ReversableModel** extends BaseModel with reversal pattern (self-referencing FK)
3. **Operation** uses proxy subclass pattern — 19+ proxy models override class attrs for type-specific behavior
4. **Transaction** uses GenericForeignKey to link back to any "document" (Operation, Adjustment)
5. **ProductLedgerEntry** is append-only with idempotency keys (DB-level unique constraint)
6. **Mixin hierarchy**: `ImmutableMixin`, `AmountCleanMixin`, `OfficerMixin`, `LinkedIssuanceTransactionMixin`, `LinkedPaymentTransactionMixin`, `LinkedRePaymentTransactionMixin` provide reusable behavior
