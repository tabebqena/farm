/**
 * money.js — shared money-display formatter (window.FarmMoney).
 *
 * Mirrors the server-side `money` template filter: Western digits, `,` thousands
 * grouping, `.` decimal, `$` prefix read from `document.body.dataset.currency`.
 *
 *   FarmMoney.format(1234.5)        -> "$1,234.50"
 *   FarmMoney.format(-1234.5)       -> "-$1,234.50"
 *   FarmMoney.signed(5)             -> "+$5.00"
 *   FarmMoney.plain(1234.5)         -> "1,234.50"
 */
(function () {
  'use strict';

  const numberFormatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function currencySymbol() {
    return (document.body && document.body.dataset.currency) || 'E£';
  }

  function toNumber(value) {
    if (value === null || value === undefined || value === '') return 0;
    const n = Number(String(value).replace(/,/g, ''));
    return isFinite(n) ? n : 0;
  }

  const FarmMoney = {
    format(value, opts) {
      const options = opts || {};
      const n = toNumber(value);
      const symbol = options.symbol !== undefined ? options.symbol : currencySymbol();
      const magnitude = numberFormatter.format(Math.abs(n));
      if (options.signed) {
        return (n < 0 ? '-' : '+') + symbol + magnitude;
      }
      return (n < 0 ? '-' : '') + symbol + magnitude;
    },

    signed(value, opts) {
      return this.format(value, Object.assign({}, opts, { signed: true }));
    },

    plain(value, opts) {
      return this.format(value, Object.assign({}, opts, { symbol: '' }));
    },
  };

  window.FarmMoney = FarmMoney;
})();
