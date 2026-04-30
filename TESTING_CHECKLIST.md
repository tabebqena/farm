# Manual Testing Checklist

## Entity Management Views (16 views)

### Core Entity Views
- [*] `entity_list_view` - List all entities
  - URL: `/entities/`
  - Test: Navigation, filtering, pagination
  - N.B:. filtering by deleted only not fully testted.
- [ ] Complete the above tests  
  
- [*] `entity_detail_view` - View entity details
  - URL: `/entities/<int:pk>/`
  - Test: Display entity info, related stakeholders, operations
  
### Person Management
- [*] `person_create_view` - Create new person
  - URL: `/entities/person/add/`
  - Test: Form validation, successful creation, redirect
  
- [*] `person_edit_view` - Edit person
  - URL: `/entities/person/edit/<int:pk>`
  - Test: Load existing data, update, validation
  
### Project Management
- [ ] `project_edit_view` - Edit project
  - URL: `/entities/project/edit/<int:pk>`
  - Test: Form functionality, update project details
  
- [ ] `project_setup_wizard_view` - Project setup wizard
  - URL: `/entities/project/setup/`
  - URL: `/entities/project/<int:entity_pk>/setup/<int:step>/`
  - Test: All wizard steps, step navigation, data persistence
  
### Contact Management
- [ ] `add_contact_info_view` - Add contact information
  - URL: `/entities/<int:entity_id>/contact/add/`
  - Test: Form, validation, creation
  
- [ ] `edit_contact_info_view` - Edit contact information
  - URL: `/entities/contact/<int:pk>/edit/`
  - Test: Load data, update, validation
  
### Stakeholder Management
- [ ] `add_vendor_view` - Add vendor stakeholder
  - URL: `/entities/project/<int:pk>/add-vendor/`
  - Test: Add vendor, validation
  
- [ ] `add_client_view` - Add client stakeholder
  - URL: `/entities/project/<int:pk>/add-client/`
  - Test: Add client, validation
  
- [ ] `add_worker_view` - Add worker stakeholder
  - URL: `/entities/project/<int:pk>/add-worker/`
  - Test: Add worker, validation
  
- [ ] `add_shareholder_view` - Add shareholder
  - URL: `/entities/project/<int:pk>/add-shareholder/`
  - Test: Add shareholder, validation
  
- [ ] `edit_stakeholder_view` - Edit stakeholder
  - URL: `/entities/stakeholder/<int:pk>/edit/`
  - Test: Load stakeholder, update, validation
  
### Category Management
- [ ] `category_relation_edit_view` - Edit category relation
  - URL: `/entities/category/edit/<int:pk>`
  - Test: Edit category assignment
  
- [ ] `category_relation_detail_view` - View category relation
  - URL: `/entities/category/detail/<int:pk>`
  - Test: Display category details
  
- [ ] `category_bulk_assign_view` - Bulk assign categories
  - URL: `/entities/<int:parent_entity_id>/category/bulk-assign/`
  - Test: Bulk assignment functionality

---

## Operation Management Views (28 views)

### Period Management
- [ ] `period_list_view` - List periods
  - URL: `/entities/operations/periods/<int:entity_pk>/`
  - Test: Display periods, filtering
  
- [ ] `period_detail_view` - View period details
  - URL: `/entities/operations/periods/<int:period_pk>/detail/`
  - Test: Display period summary, transactions
  
- [ ] `period_create_view` - Create new period
  - URL: `/entities/operations/periods/<int:entity_pk>/create/`
  - Test: Create period, validation
  
- [ ] `period_close_view` - Close period
  - URL: `/entities/operations/periods/<int:period_pk>/close/`
  - Test: Close period, prevent post-closure operations
  
### Operation List & Detail
- [ ] `operation_list_view` - List operations
  - URL: `/entities/operations/<int:person_pk>/list/`
  - Test: Display operations, filtering, pagination
  
- [ ] `operation_detail_view` - View operation details
  - URL: `/entities/operations/<int:pk>/detail/`
  - Test: Display operation data, related items
  
- [ ] `operation_update_view` - Edit operation
  - URL: `/entities/operations/<int:pk>/edit/`
  - Test: Update operation fields, validation
  
- [ ] `operation_reverse_view` - Reverse operation
  - URL: `/entities/operations/<int:pk>/reverse/`
  - Test: Reverse operation, create reversal
  
### Operation Creation
- [ ] `EvaluationCreateView` - Create evaluation
  - URL: `/entities/operations/<int:pk>/evaluate/<int:product_pk>/`
  - Test: Create evaluation, record values
  
- [ ] `BirthCreateView` - Record birth
  - URL: `/entities/operations/<int:pk>/birth/create`
  - Test: Create birth operation, add new product
  
- [ ] `DeathCreateView` - Record death
  - URL: `/entities/operations/<int:pk>/death/create`
  - Test: Create death operation, mark product as dead
  
- [ ] `OperationCreateView` - Create generic operation
  - URL: `/entities/operations/<int:pk>/<op_type>/create`
  - Test: Create various operation types
  
### Purchase Flow (9 views)
- [ ] `purchase_wizard_view` - Purchase wizard
  - URL: `/entities/operations/<int:pk>/purchase/wizard/`
  - URL: `/entities/operations/<int:pk>/purchase/wizard/<int:step>/`
  - Test: All wizard steps, data persistence
  
- [ ] `cancel_purchase_wizard_view` - Cancel purchase wizard
  - URL: `/entities/operations/<int:pk>/purchase/wizard/cancel/`
  - Test: Cancel flow, cleanup
  
- [ ] `purchase_invoice_view` - Purchase invoice
  - URL: `/entities/operations/<int:pk>/purchase/invoice/`
  - Test: Display invoice
  
- [ ] `purchase_select_template_view` - Select purchase template
  - URL: `/entities/operations/<int:pk>/purchase/invoice/select-template/`
  - Test: Template selection
  
- [ ] `purchase_add_item_view` - Add/edit purchase item
  - URL: `/entities/operations/<int:pk>/purchase/invoice/add-item/`
  - URL: `/entities/operations/<int:pk>/purchase/invoice/add-item/<int:idx>/`
  - Test: Add items, edit items, validation
  
- [ ] `purchase_delete_item_view` - Delete purchase item
  - URL: `/entities/operations/<int:pk>/purchase/invoice/delete-item/<int:idx>/`
  - Test: Delete item, update totals
  
- [ ] `purchase_submit_view` - Submit purchase
  - URL: `/entities/operations/<int:pk>/purchase/invoice/submit/`
  - Test: Submit purchase, create operation
  
### Sale Flow (9 views)
- [ ] `sale_wizard_view` - Sale wizard
  - URL: `/entities/operations/<int:pk>/sale/wizard/`
  - URL: `/entities/operations/<int:pk>/sale/wizard/<int:step>/`
  - Test: All wizard steps, data persistence
  
- [ ] `cancel_sale_wizard_view` - Cancel sale wizard
  - URL: `/entities/operations/<int:pk>/sale/wizard/cancel/`
  - Test: Cancel flow, cleanup
  
- [ ] `sale_invoice_view` - Sale invoice
  - URL: `/entities/operations/<int:pk>/sale/invoice/`
  - Test: Display invoice
  
- [ ] `sale_select_template_view` - Select sale template
  - URL: `/entities/operations/<int:pk>/sale/invoice/select-template/`
  - Test: Template selection
  
- [ ] `sale_add_item_view` - Add/edit sale item
  - URL: `/entities/operations/<int:pk>/sale/invoice/add-item/`
  - URL: `/entities/operations/<int:pk>/sale/invoice/add-item/<int:idx>/`
  - Test: Add items, edit items, validation
  
- [ ] `sale_delete_item_view` - Delete sale item
  - URL: `/entities/operations/<int:pk>/sale/invoice/delete-item/<int:idx>/`
  - Test: Delete item, update totals
  
- [ ] `sale_submit_view` - Submit sale
  - URL: `/entities/operations/<int:pk>/sale/invoice/submit/`
  - Test: Submit sale, create operation
  
- [ ] `SaleCreateView` - Create sale
  - URL: `/entities/operations/<int:pk>/sale/create`
  - Test: Create sale operation
  
### Transaction Recording
- [ ] `record_transaction_repayment` - Record loan repayment
  - URL: `/entities/operations/repayment/<int:pk>/create`
  - Test: Record repayment transaction
  
- [ ] `record_transaction_payment` - Record payment
  - URL: `/entities/operations/payment/<int:pk>/create`
  - Test: Record payment transaction

---

## Inventory Management Views (7 views)

- [ ] `stock_detail` - View stock
  - URL: `/inventory/entity/<int:entity_pk>/stock/`
  - Test: Display stock levels, products
  
- [ ] `product_detail` - View product details
  - URL: `/inventory/products/<int:pk>/`
  - Test: Display product info, ledger entries
  
- [ ] `entity_product_templates_list` - List product templates
  - URL: `/inventory/entity/<int:entity_pk>/product-templates/`
  - Test: Display available templates
  
- [ ] `project_product_templates_setup` - Setup product templates
  - URL: `/inventory/entity/<int:entity_pk>/product-templates/manage/`
  - Test: Configure templates for project
  
- [ ] `product_template_detail` - View template details
  - URL: `/inventory/product-templates/<int:pk>/`
  - Test: Display template information
  
- [ ] `create_product_template` - Create product template
  - URL: `/inventory/product-templates/create/`
  - Test: Create new template, validation
  
- [ ] `create_inventory_movement` - Create inventory movement
  - URL: `/inventory/operations/<int:operation_pk>/movement/create/`
  - Test: Record inventory movement, validate stock

---

## Authentication Views (1 view)

- [ ] `register` - User registration
  - URL: `/auth/register/`
  - Test: Registration form, validation, user creation

---

## Testing Notes

### Before Starting
- [ ] Start development server: `python manage.py runserver`
- [ ] Create test data (entities, products, operations)
- [ ] Have test users/credentials ready

### For Each View Test
- [ ] Verify page loads without errors
- [ ] Test form submissions (if applicable)
- [ ] Test validation messages
- [ ] Check navigation between related views
- [ ] Verify data persistence
- [ ] Test with different user roles (if applicable)
- [ ] Check responsive design on mobile
- [ ] Look for console errors (browser dev tools)

### Known Constraints
- SOLD/DEAD products cannot be used in new operations (except reversals, adjustments, movements)
- Closed periods prevent new operations
- Some features may be incomplete or under development

---

**Last Updated:** 2026-04-28
**Total Views to Test:** 52
