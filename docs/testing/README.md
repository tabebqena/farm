# Testing Documentation

- [GET Request Test Suite Summary](GET_REQUEST_TEST_SUITE_SUMMARY.md) - GET request test details

## Automated UI (browser) test suite

Spec-driven, real-browser UI tests live in `ui_tests/` (Selenium WebDriver +
Django `LiveServerTestCase`). Every test opens a browser, performs setup, executes
**one spec clause**, and asserts the visible response.

- **Harness:** `ui_tests/base.py` (`UiTestCase`)
- **Clause registry + drift guard:** `ui_tests/manifest.py` (`UI_CLAUSE_MANIFEST`)
- **Coverage:** op_1 (cash injection), one-shot ops (op_2–op_7, op_15), payable
  ops (op_8 loan, op_11 worker advance), and global auth/entities/cross-cutting.
- **Run:** `python3 manage.py test ui_tests --keepdb` (serial — `LiveServerTestCase`
  does not support `--parallel`; ~44 tests).
- **Artifacts:** failures save screenshot + HTML to `test_screenshots/`.
- **Env vars:** `FARM_UI_HEADFUL=1` (visible browser), `FARM_UI_BROWSER=firefox`.
- **Plan:** `ai-plans/auto-ui-test-suite-plan.md` (implementation status included).

> Note: this suite is separate from the parallel model/engine suites and must run
> serially.
