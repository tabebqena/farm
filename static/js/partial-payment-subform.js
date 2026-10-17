(function () {
    document.addEventListener("DOMContentLoaded", () => {
        const cfg = window.OperationConfig;

        // DOM Elements
        const totalInput = document.getElementById("id_total_amount");
        const paidInput = document.getElementById("id_amount_paid");
        const partialToggle = document.getElementById("enable-partial");
        const completeToggle = document.getElementById("enable-complete");
        const remainingText = document.getElementById("remaining-balance-text");
        const paymentErrorEle = document.getElementById("payment-error");
        const paymentErrorTextEle = document.getElementById("payment-error-text");
        const partialPaymentContainer = document.getElementById("partial-payment-container");
        const partialPaymentInputContainer = document.getElementById("partial-payment-input");
        const fullPaymentNotice = document.getElementById("full-payment-notice");

        // Re-entrancy guard: AmountInput.setValue dispatches native input/change
        // events, which would otherwise re-trigger syncPayment in a loop.
        let syncing = false;

        function showError(message) {
            paymentErrorEle?.classList.remove("d-none");
            if (paymentErrorTextEle) paymentErrorTextEle.innerText = message;
        }

        function hideError() {
            paymentErrorEle?.classList.add("d-none");
        }

        function setRemaining(value) {
            if (remainingText) {
                remainingText.textContent = window.FarmMoney.format(value);
            }
        }

        function setContainerActive(active) {
            if (partialPaymentContainer) {
                partialPaymentContainer.style.opacity = active ? "1" : "0.3";
            }
        }

        /**
         * Core logic to sync UI states based on payment rules.
         */
        function syncPayment() {
            if (syncing || !totalInput) return;
            syncing = true;
            try {
                const total = window.AmountInput.getNumber(totalInput);
                const isPartialChecked = !!partialToggle?.checked;
                const isCompleteChecked = !!completeToggle?.checked;

                // 1. If operation cannot have payments (e.g. just an invoice issuance)
                if (!cfg.canPay) {
                    if (paidInput) {
                        window.AmountInput.setValue(paidInput, 0);
                        paidInput.readOnly = true;
                    }
                    setContainerActive(false);
                    partialPaymentInputContainer?.classList.add("d-none");
                    fullPaymentNotice?.classList.add("d-none");
                    setRemaining(0);
                    hideError();
                    return;
                }

                // 2. Complete payment: the whole total is paid now.
                if (isCompleteChecked) {
                    window.AmountInput.setValue(paidInput, total);
                    if (paidInput) paidInput.readOnly = true;
                    setContainerActive(true);
                    partialPaymentInputContainer?.classList.add("d-none");
                    fullPaymentNotice?.classList.remove("d-none");
                    setRemaining(0);
                    hideError();
                    return;
                }

                fullPaymentNotice?.classList.add("d-none");

                // 3. Partial payment: user enters the amount paid now.
                if (cfg.isPartiallyPayable && isPartialChecked) {
                    const paid = window.AmountInput.getNumber(paidInput);
                    setRemaining(total - paid);
                    if (paidInput) paidInput.readOnly = false;
                    setContainerActive(true);
                    partialPaymentInputContainer?.classList.remove("d-none");
                    validateAmount(total, paid);
                    return;
                }

                // 4. No payment now: the full amount stays outstanding.
                window.AmountInput.setValue(paidInput, 0);
                if (paidInput) paidInput.readOnly = true;
                setContainerActive(false);
                partialPaymentInputContainer?.classList.add("d-none");
                setRemaining(total);
                hideError();
            } finally {
                syncing = false;
            }
        }

        /**
         * Validates that the paid amount does not exceed the total.
         */
        function validateAmount(total, paid) {
            if (paid > total) {
                showError(`You can't pay more than ${window.FarmMoney.format(total)}`);
            } else {
                hideError();
            }
        }

        // --- Event Listeners ---

        if (completeToggle) {
            completeToggle.addEventListener("change", () => {
                if (completeToggle.checked && partialToggle) {
                    partialToggle.checked = false;
                }
                syncPayment();
            });
        }

        if (partialToggle) {
            partialToggle.addEventListener("change", () => {
                if (partialToggle.checked) {
                    completeToggle && (completeToggle.checked = false);
                    paidInput?.focus();
                }
                syncPayment();
            });
        }

        // Listen for total / paid changes. "input", "keyup" and "change" cover
        // direct typing (IMask only emits its own "accept" event, not native
        // input events), arrow stepping and the +/- buttons.
        [totalInput, paidInput].forEach(el => {
            if (!el) return;
            ["input", "keyup", "change"].forEach(evt =>
                el.addEventListener(evt, syncPayment)
            );
            // Hook IMask directly so direct typing always re-syncs, regardless
            // of native event behaviour.
            const inst = window.AmountInput?.getInstance?.(el);
            if (inst && inst.mask) {
                inst.mask.on("accept", syncPayment);
            }
        });

        // Initial Run
        syncPayment();
    });
})();
