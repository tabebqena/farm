(function () {
    document.addEventListener("DOMContentLoaded", () => {
        const cfg = window.OperationConfig;
        const totalInput = document.getElementById("id_total_amount");
        const paidInput = document.getElementById("id_amount_paid");
        const partialToggle = document.getElementById("enable-partial");
        const remainingText = document.getElementById("remaining-balance-text");

        const partialContainer = document.getElementById("partial-payment-input");
        const fullNotice = document.getElementById("full-payment-notice");
        const amountPaidInput = document.getElementById("id_amount_paid");
        const totalAmountInput = document.getElementById("id_total_amount");

        const paymentErrorEle = document.getElementById("payment-error");
        const paymentErrorTextEle = document.getElementById("payment-error-text");


        function syncPayment() {
            const total = parseFloat(totalInput.value) || 0;


            // Possibility 1: Not payable at all (Issued only)
            if (!cfg.canPay) {
                if (paidInput) paidInput.value = 0;
                return;
            }

            // Possibility 2: Partially Payable
            if (cfg.isPartiallyPayable && partialToggle?.checked) {
                // We leave paidInput alone for the user to edit
                const paid = parseFloat(paidInput.value) || 0;
                const balance = total - paid;
                remainingText.textContent = "$ " + balance.toFixed(2);
            }
            // Possibility 3: Must be Fully Paid
            else {
                if (paidInput) {
                    paidInput.value = total.toFixed(2);
                    paidInput.readOnly = true; // Lock it if not partially payable
                }
            }
        }

        // Event Listeners
        if (partialToggle) {
            partialToggle.addEventListener("change", () => {
                console.log("changed", partialToggle.checked, paidInput)
                if (partialToggle.checked) {
                    partialContainer.classList.remove("d-none");
                    // fullNotice.classList.add("d-none");
                    amountPaidInput.focus();
                } else {
                    partialContainer.classList.add("d-none");
                    // fullNotice.classList.remove("d-none");
                    amountPaidInput.value = "";
                }
                if (paidInput) {
                    paidInput.readOnly = !partialToggle.checked;
                    if (!partialToggle.checked) {
                        paidInput.value = totalInput.value;
                    }
                }

                syncPayment();
            });
        }
        function onPaymentChanged() {
            syncPayment()
            let paid = paidInput.value;
            console.log("paid", paid)
            console.log("totalAmountInput:", totalAmountInput.value)
            if (paid > totalAmountInput.value) {
                paymentErrorEle.classList.remove("d-none");
                paymentErrorTextEle.innerText = "You can't pay more than " + totalAmountInput.value
            } else {
                paymentErrorEle.classList.add("d-none");
            }
        }
        // Sync whenever total changes or user types in paid amount
        totalInput?.addEventListener("input", syncPayment);
        paidInput?.addEventListener("input", (changeEvent) => {
            onPaymentChanged();
            // syncPayment
        });
        paidInput?.addEventListener("change", (changeEvent) => {
            onPaymentChanged();
            // syncPayment
        });


        // Initial Run
        syncPayment();
    });
})();