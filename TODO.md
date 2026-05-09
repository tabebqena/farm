# Implementation: Add group_key to InventoryMovementLine

- [ ] 1. Add `group_key` field to `InventoryMovementLine` model
- [ ] 2. Create migration
- [ ] 3. Update `InventoryMovementLineForm` (add hidden group_key)
- [ ] 4. Update `BaseInventoryMovementLineFormSet` (auto-generate group_key)
- [ ] 5. Update `create_inventory_movement` view
- [ ] 6. Update `reverse_inventory_movement_line` view
- [ ] 7. Update `reverse_inventory_movement` view
- [ ] 8. Update `InventoryMovementLine.reverse()` model method
- [ ] 9. Update `InventoryMovement.reverse()` model method
- [ ] 10. Update purchase wizard `_do_submit`
- [ ] 11. Update sale wizard `_do_submit`
- [ ] 12. Update operation detail view (group by group_key)
- [ ] 13. Update operation detail template (show grouping)
