/**
 * AmountInputFormatter: Professional amount input with formatted display & +/- buttons
 *
 * Architecture:
 * - Visible input (type="text"): Shows formatted number (1,234.50), no name attribute
 * - Hidden input (type="hidden"): Holds clean value (1234.50), has original name
 * - +/- Buttons: Increment/decrement by 1 unit with formatting
 *
 * Real-time formatting:
 * - User types: "1234567"
 * - Display shows: "1,234,567.00" (formatted while typing)
 * - Hidden holds: "1234567.00" (clean value for server)
 */

class AmountInputFormatter {
  constructor(inputElement) {
    this.visibleInput = inputElement;
    this.hiddenInput = null;
    this.originalName = this.visibleInput.name || '';

    // Setup: convert to text input, create hidden input, add buttons
    this.setupDualInputs();
    this.setupVisualInput();
    this.createControlButtons();
    this.setupListeners();
    this.initializeValue();
  }

  /**
   * Convert visible input to text, create hidden input for submission
   */
  setupDualInputs() {
    if (!this.originalName) {
      console.warn('Amount input missing name attribute:', this.visibleInput);
      return;
    }

    // Change visible input to type="text"
    this.visibleInput.type = 'text';
    this.visibleInput.removeAttribute('name');
    this.visibleInput.dataset.originalName = this.originalName;

    // Create hidden input with original name
    this.hiddenInput = document.createElement('input');
    this.hiddenInput.type = 'hidden';
    this.hiddenInput.name = this.originalName;
    this.hiddenInput.value = this.getCleanValue(this.visibleInput.value) || '0.00';

    // Insert hidden input after visible input
    this.visibleInput.parentNode.insertBefore(this.hiddenInput, this.visibleInput.nextSibling);
  }

  /**
   * Style the visible input for better appearance
   */
  setupVisualInput() {
    this.visibleInput.setAttribute('inputmode', 'decimal');
    this.visibleInput.setAttribute('placeholder', '0.00');
    // Add data attribute to identify as amount input
    this.visibleInput.dataset.amountFormatter = 'true';
  }

  /**
   * Create +/- increment/decrement buttons
   */
  createControlButtons() {
    // Wrapper for input and buttons
    const wrapper = document.createElement('div');
    wrapper.className = 'amount-input-wrapper d-flex align-items-stretch gap-0';
    wrapper.style.cssText = 'position: relative;';

    // Minus button
    const minusBtn = document.createElement('button');
    minusBtn.type = 'button';
    minusBtn.className = 'btn btn-sm btn-outline-secondary amount-btn-minus';
    minusBtn.innerHTML = '<i class="bi bi-dash"></i>';
    minusBtn.style.cssText = 'border-radius: 4px 0 0 4px; border-right: none;';
    minusBtn.setAttribute('aria-label', 'Decrease amount');
    minusBtn.addEventListener('click', (e) => {
      e.preventDefault();
      this.increment(-this.getStep());
    });

    // Plus button
    const plusBtn = document.createElement('button');
    plusBtn.type = 'button';
    plusBtn.className = 'btn btn-sm btn-outline-secondary amount-btn-plus';
    plusBtn.innerHTML = '<i class="bi bi-plus"></i>';
    plusBtn.style.cssText = 'border-radius: 0 4px 4px 0; border-left: none;';
    plusBtn.setAttribute('aria-label', 'Increase amount');
    plusBtn.addEventListener('click', (e) => {
      e.preventDefault();
      this.increment(this.getStep());
    });

    // Insert buttons after input
    const inputGroup = this.visibleInput.parentNode;
    inputGroup.insertBefore(minusBtn, this.visibleInput.nextSibling);
    inputGroup.insertBefore(plusBtn, minusBtn.nextSibling);

    this.minusBtn = minusBtn;
    this.plusBtn = plusBtn;
  }

  /**
   * Increment/decrement amount by delta
   */
  increment(delta) {
    const currentValue = this.getCleanValueAsNumber(this.visibleInput.value);
    const newValue = currentValue + delta;

    // Don't allow negative values (optional - adjust based on requirements)
    if (newValue < 0) {
      this.visibleInput.value = '0.00';
    } else {
      const normalized = newValue.toFixed(2);
      this.formatAndSync(normalized);
    }

    // Focus and select text for quick re-edit
    this.visibleInput.focus();
    this.visibleInput.select();
  }

  setupListeners() {
    this.visibleInput.addEventListener('input', () => this.onInput());
    this.visibleInput.addEventListener('blur', () => this.onBlur());
    this.visibleInput.addEventListener('keydown', (e) => this.onKeyDown(e));
  }

  /**
   * Handle arrow keys: Up/Down arrows increment/decrement amount
   */
  onKeyDown(e) {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.increment(this.getStep());
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.increment(-this.getStep());
    }
  }

  /**
   * Initialize with formatted value on page load
   */
  initializeValue() {
    const currentValue = this.visibleInput.value;
    if (currentValue && currentValue !== '0') {
      const cleaned = this.getCleanValue(currentValue);
      this.formatAndSync(cleaned);
    } else {
      this.visibleInput.value = '0.00';
      if (this.hiddenInput) this.hiddenInput.value = '0.00';
    }
  }

  /**
   * On input: real-time validation & formatting
   * User sees: 1,234.56 while typing
   * Preserves cursor position while formatting
   */
  onInput() {
    // Save current cursor position
    const cursorPos = this.visibleInput.selectionStart;
    const oldValue = this.visibleInput.value;

    let value = oldValue;

    // Allow only digits, decimal point, and minus sign
    value = value.replace(/[^\d.-]/g, '');

    // Ensure only one decimal point
    const parts = value.split('.');
    if (parts.length > 2) {
      value = parts[0] + '.' + parts[1];
    }

    // Limit to 2 decimal places
    if (parts.length === 2 && parts[1].length > 2) {
      value = parts[0] + '.' + parts[1].substring(0, 2);
    }

    // Handle empty input
    if (value === '' || value === '-' || value === '.') {
      this.visibleInput.value = value; // Keep for editing
      if (this.hiddenInput) this.hiddenInput.value = '0.00';
      // Restore cursor position
      setTimeout(() => {
        this.visibleInput.setSelectionRange(cursorPos, cursorPos);
      }, 0);
      return;
    }

    // Parse and get clean number
    const numValue = parseFloat(value || 0);
    if (isNaN(numValue)) {
      this.visibleInput.value = value;
      // Restore cursor position
      setTimeout(() => {
        this.visibleInput.setSelectionRange(cursorPos, cursorPos);
      }, 0);
      return;
    }

    // Format with thousands separator WHILE TYPING
    const normalized = numValue.toFixed(2);
    const formatted = parseFloat(normalized).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

    // Calculate cursor position adjustment
    // Count how many commas were added
    const oldCommas = (oldValue.match(/,/g) || []).length;
    const newCommas = (formatted.match(/,/g) || []).length;
    const commasAdded = newCommas - oldCommas;

    // Update visible with formatted display
    this.visibleInput.value = formatted;

    // Update hidden with clean value
    if (this.hiddenInput) {
      this.hiddenInput.value = normalized;
    }

    // Restore cursor position (adjusted for added commas)
    const newCursorPos = Math.min(cursorPos + commasAdded, formatted.length);
    setTimeout(() => {
      this.visibleInput.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  }

  /**
   * On blur: ensure proper formatting
   */
  onBlur() {
    const value = this.visibleInput.value.trim();

    if (value === '' || value === '-' || value === '.') {
      this.visibleInput.value = '0.00';
      if (this.hiddenInput) this.hiddenInput.value = '0.00';
      return;
    }

    const cleaned = this.getCleanValue(value);
    this.formatAndSync(cleaned);
  }

  /**
   * Format value and sync to both inputs
   */
  formatAndSync(cleanValue) {
    try {
      const numValue = parseFloat(cleanValue || 0);

      if (isNaN(numValue)) {
        this.visibleInput.value = '0.00';
        if (this.hiddenInput) this.hiddenInput.value = '0.00';
        return;
      }

      // Normalize to 2 decimals
      const normalized = numValue.toFixed(2);

      // Format for display
      const formatted = parseFloat(normalized).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });

      // Update both inputs
      this.visibleInput.value = formatted;
      if (this.hiddenInput) {
        this.hiddenInput.value = normalized;
      }
    } catch (e) {
      console.warn('Amount formatting error:', e);
    }
  }

  /**
   * Extract clean numeric value from formatted string
   * "1,234.56" → "1234.56"
   */
  getCleanValue(formattedValue) {
    if (!formattedValue) return '0.00';
    return formattedValue.replace(/,/g, '').trim();
  }

  /**
   * Get clean value as number
   * "1,234.56" → 1234.56
   */
  getCleanValueAsNumber(formattedValue) {
    const clean = this.getCleanValue(formattedValue);
    return parseFloat(clean) || 0;
  }

  /**
   * Get step value from input attribute (default 0.01 for currency)
   * step="1" → 1
   * step="0.01" → 0.01
   * no step → 0.01 (default)
   */
  getStep() {
    const step = this.visibleInput.getAttribute('step');
    if (step && !isNaN(parseFloat(step))) {
      return parseFloat(step);
    }
    return 0.01; // Default step for currency amounts
  }
}

/**
 * Initialize all amount inputs on page load
 */
document.addEventListener('DOMContentLoaded', () => {
  const amountInputs = document.querySelectorAll('input.amount-input');
  amountInputs.forEach((input) => {
    new AmountInputFormatter(input);
  });
});

/**
 * Handle dynamically added inputs (for Django formsets)
 */
document.addEventListener('formset:added', (event) => {
  const newRow = event.detail.formsetRow || event.target.closest('.formset-row');
  if (newRow) {
    const newInputs = newRow.querySelectorAll('input.amount-input');
    newInputs.forEach((input) => {
      // Skip if already initialized
      if (!input.dataset.amountFormatter) {
        new AmountInputFormatter(input);
      }
    });
  }
});

/**
 * Observe for dynamically added inputs (MutationObserver)
 */
const observerConfig = { childList: true, subtree: true };
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    if (mutation.type === 'childList') {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) { // Element node
          const amountInputs = node.querySelectorAll?.('input.amount-input') || [];
          amountInputs.forEach((input) => {
            // Only init if not already initialized
            if (!input.dataset.amountFormatter) {
              new AmountInputFormatter(input);
            }
          });
        }
      });
    }
  });
});

// Start observing after page load
document.addEventListener('DOMContentLoaded', () => {
  observer.observe(document.body, observerConfig);
});
