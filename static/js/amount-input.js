/**
 * amount-input.js — Formatted money/quantity inputs backed by IMask.
 *
 * Replaces the previous hand-rolled AmountInputFormatter. Formatting and caret
 * handling are delegated to IMask's Number mask, which tracks the caret by
 * digit instead of by raw index, so typing across the decimal point no longer
 * forces the cursor back.
 *
 * Architecture (unchanged from before, for server compatibility):
 *   - Visible input  : type="text", no name, shows "1,234.50"
 *   - Hidden  input  : type="hidden", keeps the original name, holds "1234.50"
 *   - +/- buttons and Arrow Up/Down stepping are preserved.
 *
 * Public API (window.AmountInput):
 *   getValue(elOrId)      -> clean string, e.g. "1234.50"
 *   getNumber(elOrId)     -> number
 *   setValue(elOrId, val) -> updates masked display + hidden twin, fires events
 *   getInstance(el)       -> AmountInput instance or undefined
 */
(function () {
  'use strict';

  if (typeof IMask === 'undefined') {
    console.error('amount-input.js: IMask is not loaded. Include js/vendor/imask.min.js first.');
    return;
  }

  /** WeakMap is the source of truth for "already initialised". Cloned DOM nodes
   *  keep attributes but lose the WeakMap entry, so formset clones re-init. */
  const instances = new WeakMap();

  function cleanForServer(raw) {
    if (raw === '' || raw === null || raw === undefined) return '0.00';
    const n = Number(String(raw).replace(/,/g, ''));
    if (!isFinite(n)) return '0.00';
    return n.toFixed(2);
  }

  function resolve(elOrId) {
    if (!elOrId) return null;
    if (typeof elOrId === 'string') return document.getElementById(elOrId);
    return elOrId;
  }

  class AmountInput {
    constructor(input) {
      this.visibleInput = input;
      this.originalName = input.dataset.originalName || input.name || '';
      this.readOnly = input.readOnly || input.hasAttribute('readonly');
      this.hiddenInput = null;
      this.mask = null;

      if (!this.originalName) {
        console.warn('Amount input missing name attribute:', input);
        return;
      }

      // First conversion: turn the number/text input into the visible half.
      if (!input.dataset.originalName) {
        input.type = 'text';
        input.removeAttribute('name');
        input.dataset.originalName = this.originalName;
      }
      input.dataset.amountFormatter = 'true';

      this.hiddenInput = this.findHiddenInput() || this.createHiddenInput();

      input.setAttribute('inputmode', 'decimal');
      input.setAttribute('dir', 'ltr');
      input.setAttribute('autocomplete', 'off');
      if (!input.getAttribute('placeholder')) input.setAttribute('placeholder', '0.00');

      if (!this.readOnly) this.setupButtons();

      this.setupMask();
      this.setupListeners();
      this.initialiseValue();
    }

    findHiddenInput() {
      const parent = this.visibleInput.parentNode;
      const byName = (root) =>
        root && root.querySelector('input[type="hidden"][name="' + this.originalName + '"]');
      return byName(parent) || byName(document) || null;
    }

    createHiddenInput() {
      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = this.originalName;
      if (this.visibleInput.id) hidden.dataset.originalId = this.visibleInput.id;
      this.visibleInput.parentNode.insertBefore(hidden, this.visibleInput.nextSibling);
      return hidden;
    }

    setupButtons() {
      const parent = this.visibleInput.parentNode;
      let minus = parent.querySelector('.amount-btn-minus');
      let plus = parent.querySelector('.amount-btn-plus');

      if (!minus) {
        minus = document.createElement('button');
        minus.type = 'button';
        minus.className = 'btn btn-sm btn-outline-secondary amount-btn-minus';
        minus.innerHTML = '<i class="bi bi-dash"></i>';
        minus.setAttribute('aria-label', 'Decrease amount');
        parent.insertBefore(minus, this.visibleInput.nextSibling);
      }
      if (!plus) {
        plus = document.createElement('button');
        plus.type = 'button';
        plus.className = 'btn btn-sm btn-outline-secondary amount-btn-plus';
        plus.innerHTML = '<i class="bi bi-plus"></i>';
        plus.setAttribute('aria-label', 'Increase amount');
        parent.insertBefore(plus, minus.nextSibling);
      }

      minus.addEventListener('click', (e) => {
        e.preventDefault();
        this.increment(-this.getStep());
      });
      plus.addEventListener('click', (e) => {
        e.preventDefault();
        this.increment(this.getStep());
      });
    }

    setupMask() {
      this.mask = IMask(this.visibleInput, {
        mask: Number,
        scale: 2,
        thousandsSeparator: ',',
        radix: '.',
        padFractionalZeros: true,
        normalizeZeros: true,
        signed: false,
      });
      this.mask.on('accept', () => this.syncHidden(this.mask.unmaskedValue));
    }

    setupListeners() {
      this.visibleInput.addEventListener('focus', () => {
        if (this.mask) this.mask.updateOptions({ padFractionalZeros: false });
      });
      this.visibleInput.addEventListener('blur', () => this.onBlur());
      this.visibleInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          this.increment(this.getStep());
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          this.increment(-this.getStep());
        }
      });
    }

    initialiseValue() {
      const raw = (this.visibleInput.value || '').trim();
      const normalised = raw === '' ? '0.00' : cleanForServer(raw);
      this.mask.value = normalised;
      this.syncHidden(this.mask.unmaskedValue);
    }

    onBlur() {
      if (!this.mask) return;
      this.mask.updateOptions({ padFractionalZeros: true });
      const raw = this.mask.unmaskedValue;
      this.mask.value = raw === '' ? '0.00' : cleanForServer(raw);
      this.syncHidden(this.mask.unmaskedValue);
    }

    increment(delta) {
      const current = Number(this.mask.unmaskedValue) || 0;
      let next = current + delta;
      if (next < 0) next = 0;
      this.setValue(next.toFixed(2));
      this.visibleInput.focus();
      this.visibleInput.select();
    }

    setValue(value) {
      const isEmpty = value === '' || value === null || value === undefined;
      const num = isEmpty ? null : Number(String(value).replace(/,/g, ''));
      this.mask.updateOptions({ padFractionalZeros: true });
      if (num === null || !isFinite(num)) {
        this.mask.value = '';
        this.syncHidden('');
      } else {
        this.mask.value = num.toFixed(2);
        this.syncHidden(num.toFixed(2));
      }
      this.visibleInput.dispatchEvent(new Event('input', { bubbles: true }));
      this.visibleInput.dispatchEvent(new Event('change', { bubbles: true }));
    }

    getStep() {
      const step = this.visibleInput.getAttribute('step');
      if (step && !isNaN(parseFloat(step))) return parseFloat(step);
      return 0.01;
    }

    syncHidden(raw) {
      if (!this.hiddenInput) return;
      const value = cleanForServer(raw);
      if (this.hiddenInput.value === value) return;
      this.hiddenInput.value = value;
      this.hiddenInput.dispatchEvent(new Event('input', { bubbles: true }));
      this.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function init(input) {
    if (!input || instances.has(input)) return;
    instances.set(input, new AmountInput(input));
  }

  function initAll(root) {
    (root || document).querySelectorAll('input.amount-input').forEach(init);
  }

  const AmountInputAPI = {
    init,
    initAll,

    getInstance(el) {
      return instances.get(el);
    },

    getValue(elOrId) {
      const el = resolve(elOrId);
      if (!el) return '0.00';
      if (el.type === 'hidden') return el.value;
      const inst = instances.get(el);
      if (inst && inst.hiddenInput) return inst.hiddenInput.value;
      return cleanForServer(el.value);
    },

    getNumber(elOrId) {
      return parseFloat(this.getValue(elOrId)) || 0;
    },

    setValue(elOrId, value) {
      const el = resolve(elOrId);
      if (!el) return;
      const inst = instances.get(el);
      if (inst) {
        inst.setValue(value);
        return;
      }
      // Not yet initialised: write through to the hidden twin if there is one.
      const name = el.dataset.originalName || el.name;
      const hidden = name
        ? document.querySelector('input[type="hidden"][name="' + name + '"]')
        : null;
      if (hidden) hidden.value = cleanForServer(value);
      el.value = value === '' ? '' : cleanForServer(value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    },
  };

  window.AmountInput = AmountInputAPI;

  document.addEventListener('DOMContentLoaded', () => initAll(document));

  document.addEventListener('formset:added', (event) => {
    const row =
      (event.detail && event.detail.formsetRow) ||
      (event.target && event.target.closest && event.target.closest('.formset-row'));
    if (row) initAll(row);
  });

  document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches('input.amount-input')) init(node);
          if (node.querySelectorAll) initAll(node);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
