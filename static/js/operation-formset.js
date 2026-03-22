/**
 * Handles Django Formset dynamic rows and row-level calculations
 */
(function () {
    document.addEventListener("DOMContentLoaded", function () {
        const tableBody = document.getElementById("item-formset-body");
        const addButton = document.getElementById("add-item-row");
        const totalAmountInput = document.getElementById("id_total_amount");
        const prefix = window.OperationConfig.formsetPrefix;
        const totalForms = document.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);

        function calculateTotals_() {
            let grandTotal = 0;
            document.querySelectorAll(".item-row").forEach((row) => {
                const qty = parseFloat(row.querySelector(".qty-input").value) || 0;
                const price = parseFloat(row.querySelector(".price-input").value) || 0;
                const rowTotal = qty * price;
                row.querySelector(".row-total").textContent = "$ " + rowTotal.toFixed(2);
                grandTotal += rowTotal;
            });

            if (totalAmountInput) {
                totalAmountInput.value = grandTotal.toFixed(2);
                // Dispatch event so other scripts (like partial payment) know the total changed
                totalAmountInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }


        function calculateTotals() {
            let grandTotal = 0;
            document.querySelectorAll(".item-row").forEach((row) => {
                const qty = parseFloat(row.querySelector(".qty-input").value) || 0;
                const price = parseFloat(row.querySelector(".price-input").value) || 0;
                const rowTotal = qty * price;
                row.querySelector(".row-total").textContent = "$ " + rowTotal.toFixed(2);
                grandTotal += rowTotal;
            });

            if (totalAmountInput) {
                totalAmountInput.value = grandTotal.toFixed(2);
                // Trigger 'input' so the Payment script hears the change
                totalAmountInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        if (addButton) {
            addButton.addEventListener("click", function () {
                const currentCount = parseInt(totalForms.value);
                const rows = tableBody.getElementsByClassName("item-row");
                const newRow = rows[0].cloneNode(true);

                const regex = new RegExp(`-${currentCount - 1}-`, "g");
                newRow.innerHTML = newRow.innerHTML.replace(regex, `-${currentCount}-`);

                newRow.querySelectorAll("input").forEach((input) => {
                    if (input.type !== "hidden") input.value = "";
                    if (input.classList.contains("qty-input")) input.value = "1";
                });
                newRow.querySelector(".row-total").textContent = "$ 0.00";

                tableBody.appendChild(newRow);
                totalForms.value = currentCount + 1;
            });
        }

        tableBody?.addEventListener("click", function (e) {
            if (e.target.closest(".remove-row")) {
                const rows = tableBody.getElementsByClassName("item-row");
                if (rows.length > 1) {
                    e.target.closest(".item-row").remove();
                    calculateTotals();
                    totalForms.value = document.getElementsByClassName("item-row").length;
                }
            }
        });

        tableBody?.addEventListener("input", function (e) {
            if (e.target.classList.contains("qty-input") || e.target.classList.contains("price-input")) {
                calculateTotals();
            }
        });

        // Initial calculation
        calculateTotals();
    });
})();