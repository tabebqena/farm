/**
 * item-quantity-validation.js — per-item unit-consistency guard.
 *
 * Every invoice item's quantity must be a positive multiple of its product
 * template's `minimum_quantity` increment (1 for Head, 0.01 for Kg, ...).
 * The item forms are rendered with `novalidate`, so the browser's native
 * `step` check is disabled and e.g. "1.5 Head" slips through to the session.
 * This script restores that check client-side and blocks submission while any
 * item is invalid.
 *
 * The increment is resolved per item, in order:
 *   1. the quantity input's own `data-minimum-quantity` attribute;
 *   2. the selected `<option data-minimum-quantity>` of the row's
 *      `.product-select` (create-mode formsets — the rule adapts to whichever
 *      template each item references);
 *   3. the input's `step` attribute.
 *
 * Public API (window.ItemQuantity):
 *   validate(input)      -> boolean   validate a single quantity input
 *   validateForm(form)   -> boolean   validate every item in a form
 *   validateAll(root)    -> boolean   validate across a subtree
 *
 * The error text can be localised per input via `data-error-message`
 * (placeholders `{qty}` / `{min}`) and `data-error-positive`; English
 * fallbacks are used otherwise.
 */
(function () {
  'use strict';

  var DEFAULT_MESSAGE = 'Quantity must be a multiple of the minimum increment {min}.';
  var DEFAULT_POSITIVE = 'Quantity must be greater than zero.';

  function toNumber(value) {
    if (value === null || value === undefined || value === '') return NaN;
    var n = Number(String(value).replace(/,/g, ''));
    return isFinite(n) ? n : NaN;
  }

  function getValue(input) {
    if (window.AmountInput) return window.AmountInput.getValue(input);
    return (input.value || '').trim();
  }

  function decimals(value) {
    var s = String(value);
    var dot = s.indexOf('.');
    return dot === -1 ? 0 : s.length - dot - 1;
  }

  /** True when *value* is an integer multiple of *step* (both decimal). */
  function isMultiple(value, step) {
    var v = toNumber(value);
    var s = toNumber(step);
    if (!isFinite(v) || !isFinite(s) || s <= 0) return true;
    var scale = Math.pow(10, Math.max(decimals(value), decimals(step), 2));
    var iv = Math.round(v * scale);
    var istep = Math.round(s * scale);
    if (istep === 0) return true;
    return iv % istep === 0;
  }

  function incrementOf(input) {
    if (input.dataset.minimumQuantity) return toNumber(input.dataset.minimumQuantity);
    var row = input.closest('.item-row');
    var select = row && row.querySelector('.product-select');
    if (select && select.value) {
      var opt = select.options[select.selectedIndex];
      if (opt && opt.dataset.minimumQuantity) return toNumber(opt.dataset.minimumQuantity);
    }
    var step = input.getAttribute('step');
    return step ? toNumber(step) : NaN;
  }

  /** An item is only validated once it references a product and is not removed. */
  function isActive(input) {
    var row = input.closest('.item-row');
    if (!row) return true;
    if (row.classList.contains('d-none')) return false;
    var del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
    if (del && del.checked) return false;
    var select = row.querySelector('.product-select');
    if (select && !select.value) return false;
    return true;
  }

  function errorSlot(input) {
    var scope = input.closest('.item-row, .mb-3, .col-12, .card-body') || input.parentNode;
    var slot = scope.querySelector('.js-quantity-error');
    if (slot) return slot;
    slot = document.createElement('div');
    slot.className = 'js-quantity-error invalid-feedback d-block small text-danger';
    slot.hidden = true;
    var anchor = input.closest('.input-group') || input;
    anchor.parentNode.insertBefore(slot, anchor.nextSibling);
    return slot;
  }

  function fill(template, values) {
    return template.replace(/\{(\w+)\}/g, function (match, key) {
      return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match;
    });
  }

  function setError(input, message) {
    var slot = errorSlot(input);
    if (message) {
      slot.textContent = message;
      slot.hidden = false;
      input.classList.add('is-invalid');
      return false;
    }
    slot.textContent = '';
    slot.hidden = true;
    input.classList.remove('is-invalid');
    return true;
  }

  function validate(input) {
    if (!isActive(input)) return setError(input, '');
    var min = incrementOf(input);
    if (isFinite(min) && min > 0) input.setAttribute('step', String(min));

    var raw = getValue(input);
    var value = toNumber(raw);

    if (!isFinite(value) || value <= 0) {
      return setError(input, input.dataset.errorPositive || DEFAULT_POSITIVE);
    }
    if (isFinite(min) && min > 0 && !isMultiple(value, min)) {
      var message = input.dataset.errorMessage || DEFAULT_MESSAGE;
      return setError(input, fill(message, { qty: raw, min: min }));
    }
    return setError(input, '');
  }

  function quantityInputs(root) {
    return (root || document).querySelectorAll('.qty-input, .amount-input[data-minimum-quantity]');
  }

  function validateAll(root) {
    var valid = true;
    var firstInvalid = null;
    quantityInputs(root).forEach(function (input) {
      if (!validate(input) && !firstInvalid) firstInvalid = input;
    });
    if (firstInvalid) {
      valid = false;
      firstInvalid.focus();
    }
    return valid;
  }

  function validateForm(form) {
    return validateAll(form);
  }

  function bindForm(form) {
    if (form.dataset.itemQuantityBound) return;
    form.dataset.itemQuantityBound = 'true';
    form.addEventListener('submit', function (e) {
      if (!validateForm(form)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  }

  function bindInput(input) {
    if (input.dataset.itemQuantityBound) return;
    input.dataset.itemQuantityBound = 'true';
    input.addEventListener('blur', function () {
      validate(input);
    });
    input.addEventListener('change', function () {
      validate(input);
    });
  }

  function setup(root) {
    quantityInputs(root).forEach(function (input) {
      bindInput(input);
      var form = input.form || input.closest('form');
      if (form) bindForm(form);
      if (input.dataset.minimumQuantity) input.setAttribute('step', input.dataset.minimumQuantity);
    });
  }

  /** Re-validate when a row's product selection (and thus its unit) changes. */
  document.addEventListener('change', function (e) {
    if (!e.target.classList || !e.target.classList.contains('product-select')) return;
    var row = e.target.closest('.item-row');
    if (!row) return;
    row.querySelectorAll('.qty-input').forEach(function (input) {
      validate(input);
    });
  });

  document.addEventListener('DOMContentLoaded', function () {
    setup(document);
  });

  /** Newly cloned formset rows opt in as they appear. */
  document.addEventListener('formset:added', function (event) {
    var row =
      (event.detail && event.detail.formsetRow) ||
      (event.target && event.target.closest && event.target.closest('.item-row'));
    if (row) setup(row);
  });

  window.ItemQuantity = {
    validate: validate,
    validateForm: validateForm,
    validateAll: validateAll,
  };
})();
