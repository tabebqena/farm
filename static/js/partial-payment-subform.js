(function () {
    document.addEventListener("DOMContentLoaded", () => {
        const cfg = window.OperationConfig;

        // DOM Elements
        const totalInput = document.getElementById("id_total_amount");
        const paidInput = document.getElementById("id_amount_paid");
        const partialToggle = document.getElementById("enable-partial");
        const remainingText = document.getElementById("remaining-balance-text");
        const paymentErrorEle = document.getElementById("payment-error");
        const paymentErrorTextEle = document.getElementById("payment-error-text");
        const partialPaymentContainer = document.getElementById("partial-payment-container")
        const partialPaymentInputContainer = document.getElementById("partial-payment-input")

        /**
         * Core logic to sync UI states based on payment rules
         */
        function syncPayment() {
            const total = parseFloat(totalInput.value) || 0;
            const isPartialChecked = partialToggle?.checked;

            // 1. If operation cannot have payments (e.g. just an invoice issuance)
            if (!cfg.canPay) {
                if (paidInput) {
                    paidInput.value = 0;
                    paidInput.readOnly = true;
                }
                return;
            }

            // 2. Logic for partial vs full payment
            if (cfg.isPartiallyPayable && isPartialChecked) {
                const paid = parseFloat(paidInput.value) || 0;
                const balance = total - paid;

                if (remainingText) {
                    remainingText.textContent = `$ ${balance.toFixed(2)}`;
                }
                paidInput.readOnly = false;
            } else {
                // 
                if (paidInput) {
                    // paidInput.value = total.toFixed(2);
                    paidInput.readOnly = true;
                }
            }

            validateAmount();
        }

        /**
         * Validates that paid amount does not exceed total
         */
        function validateAmount() {
            const total = parseFloat(totalInput.value) || 0;
            const paid = parseFloat(paidInput.value) || 0;

            if (paid > total) {
                paymentErrorEle?.classList.remove("d-none");
                if (paymentErrorTextEle) {
                    paymentErrorTextEle.innerText = `You can't pay more than ${total.toFixed(2)}`;
                }
            } else {
                paymentErrorEle?.classList.add("d-none");
            }
        }

        // --- Event Listeners ---

        if (partialToggle) {
            partialToggle.addEventListener("change", () => {
                if (partialToggle.checked) {
                    paidInput?.focus();
                    partialPaymentContainer.style.opacity = "1"
                    partialPaymentInputContainer.classList.remove("d-none")

                } else {
                    // 
                    paidInput.value = 0;//totalInput.value;
                    partialPaymentContainer.style.opacity = "0.3"
                    partialPaymentInputContainer.classList.add("d-none")

                }
                syncPayment();
            });
        }

        // Listen for changes on total or paid amount
        [totalInput, paidInput].forEach(el => {
            el?.addEventListener("input", syncPayment);
        });

        // Initial Run
        syncPayment();
    });
})();