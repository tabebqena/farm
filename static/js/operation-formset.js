/**
 * Handles Django Formset dynamic rows and row-level calculations.
 *
 * Assumptions:
 *  - Both formsets have can_delete=True, so each row contains a hidden DELETE checkbox.
 *  - Deletion hides the row and checks DELETE; TOTAL_FORMS is NOT decremented so
 *    Django sees the correct number of forms (deleted ones included).
 *  - Adding a new row clones the LAST visible row (whose index == currentCount-1)
 *    and bumps its index to currentCount.
 */
(function () {
    document.addEventListener("DOMContentLoaded", function () {
        const tableBody = document.getElementById("item-formset-body");
        const addButton = document.getElementById("add-item-row");
        const totalAmountInput = document.getElementById("id_total_amount");
        const prefix = window.OperationConfig.formsetPrefix;
        const totalForms = document.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);

        if (!tableBody || !totalForms) return;

        // ── helpers ────────────────────────────────────────────────────────────

        /** Return the DELETE checkbox inside a row, or null. */
        function getDeleteCheckbox(row) {
            return row.querySelector(`input[type="checkbox"][name$="-DELETE"]`);
        }

        /** True when the row is logically deleted (DELETE checked or DOM-hidden). */
        function isDeleted(row) {
            const cb = getDeleteCheckbox(row);
            return cb ? cb.checked : row.classList.contains("d-none");
        }

        // ── recalculate totals ─────────────────────────────────────────────────

        function calculateTotals() {
            let grandTotal = 0;

            tableBody.querySelectorAll(".item-row").forEach((row) => {
                if (isDeleted(row)) {
                    row.querySelector(".row-total").textContent = "—";
                    return;
                }
                const qty = parseFloat(row.querySelector(".qty-input").value) || 0;
                const price = parseFloat(row.querySelector(".price-input").value) || 0;
                const rowTotal = qty * price;
                row.querySelector(".row-total").textContent = "$ " + rowTotal.toFixed(2);
                grandTotal += rowTotal;
            });

            // Update footer grand-total display (desktop and mobile views)
            document.querySelectorAll(".grand-total-display").forEach((el) => {
                if (el.tagName === "INPUT") {
                    el.value = "$ " + grandTotal.toFixed(2);
                } else {
                    el.textContent = "$ " + grandTotal.toFixed(2);
                }
            });

            if (totalAmountInput) {
                totalAmountInput.value = grandTotal.toFixed(2);
            }

            // Update the standalone total-amount input (present only when no formset)
            if (totalAmountInput) {
                totalAmountInput.value = grandTotal.toFixed(2);
                totalAmountInput.dispatchEvent(new Event("input", { bubbles: true }));
            }
        }

        // ── add row ────────────────────────────────────────────────────────────

        if (addButton) {
            addButton.addEventListener("click", function () {
                let totalForms = document.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);

                const currentCount = parseInt(totalForms.value);
                const rows = tableBody.querySelectorAll(".item-row");

                // Clone the LAST row — its index is currentCount-1, matching the regex below.
                const lastRow = rows[rows.length - 1];
                const newRow = lastRow.cloneNode(true);

                // Replace every occurrence of the last index with the new index.
                const regex = new RegExp(`-${currentCount - 1}-`, "g");
                newRow.innerHTML = newRow.innerHTML.replace(regex, `-${currentCount}-`);

                // Reset inputs in the new row.
                newRow.querySelectorAll("input").forEach((input) => {
                    if (input.type === "checkbox") {
                        input.checked = false;          // uncheck DELETE
                    } else if (input.type === "hidden") {
                        // Clear the id field so the new row is treated as a new object.
                        if (input.name.endsWith("-id")) input.value = "";
                    } else {
                        input.value = "";
                    }
                    if (input.classList.contains("qty-input")) input.value = "1";
                });

                // Reset selects (product / selected_product dropdowns).
                newRow.querySelectorAll("select").forEach((sel) => {
                    sel.selectedIndex = 0;
                    sel.dispatchEvent(new Event("change", { bubbles: true }));
                });

                // Ensure the new row is visible (in case it was cloned from a deleted one).
                newRow.classList.remove("d-none");
                newRow.querySelector(".row-total").textContent = "$ 0.00";

                tableBody.appendChild(newRow);
                totalForms.value = currentCount + 1;
            });
        }

        // ── delete row ─────────────────────────────────────────────────────────

        tableBody.addEventListener("click", function (e) {
            const btn = e.target.closest(".remove-row");
            if (!btn) return;

            const visibleRows = tableBody.querySelectorAll(".item-row:not(.d-none)");
            if (visibleRows.length <= 1) return;   // keep at least one row

            const row = btn.closest(".item-row");
            const deleteCheckbox = getDeleteCheckbox(row);

            if (deleteCheckbox) {
                // can_delete=True: mark for deletion; Django handles it server-side.
                deleteCheckbox.checked = true;
                row.classList.add("d-none");
                // TOTAL_FORMS is intentionally NOT decremented.
            } else {
                // Fallback for rows without a DELETE field (shouldn't happen).
                row.remove();
                totalForms.value = tableBody.querySelectorAll(".item-row").length;
            }

            calculateTotals();
        });

        // ── live recalculation on input ────────────────────────────────────────

        tableBody.addEventListener("input", function (e) {
            if (
                e.target.classList.contains("qty-input") ||
                e.target.classList.contains("price-input")
            ) {
                calculateTotals();
            }
        });

        // Initial calculation on page load.
        calculateTotals();
    });
})();
