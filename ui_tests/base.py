"""Real-browser (Selenium) harness for the Farm UI suite.

Every test opens a real browser against the live Django server, performs setup,
executes exactly one spec clause, and asserts the visible response promised by the
spec. One clause -> one test method -> one assertion family.

Design: ai-plans/auto-ui-test-suite-plan.md
"""
import logging
import os
import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import LiveServerTestCase
from django.urls import reverse
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import Select, WebDriverWait

from apps.app_entity.models import Entity, EntityType

# Re-export the canonical fixtures so every UI test file shares the exact world
# the model/engine suite asserts on.
from apps.app_operation.tests.base import (  # noqa: F401
    make_officer,
    make_project,
    make_person,
    make_client,
    make_vendor,
    make_stakeholder,
    make_worker,
    inject_person_fund,
    inject_project_fund,
)

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "test_screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = 15


class _StaticFromDirsHandler(LiveServerTestCase.static_handler):
    """Serve static from STATICFILES_DIRS.

    The project does not set STATIC_ROOT (only STATICFILES_DIRS), so Django 6's
    default live-server static handler would crash on every /static/ request
    (document_root=None). This override keeps the real dev-server behavior.
    """

    def get_base_dir(self):
        return str(settings.STATICFILES_DIRS[0])

    def get_base_url(self):
        return settings.STATIC_URL


class UiTestCase(LiveServerTestCase):
    """Canonical world + Selenium helpers. One browser per test class."""

    static_handler = _StaticFromDirsHandler

    # ------------------------------------------------------------------
    # Browser lifecycle (one driver per class; per-test isolation via DB)
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Quiet Selenium + Django DB DEBUG noise (test-side only).
        logging.getLogger("selenium").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)
        logging.getLogger("django.db.backends").setLevel(logging.WARNING)
        browser = os.environ.get("FARM_UI_BROWSER", "chrome").lower()
        headful = os.environ.get("FARM_UI_HEADFUL") == "1"
        if browser == "firefox":
            options = FirefoxOptions()
            if not headful:
                options.add_argument("--headless")
            cls.driver = webdriver.Firefox(options=options)
        else:
            options = ChromeOptions()
            if not headful:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1366,768")
            cls.driver = webdriver.Chrome(options=options)
        cls.driver.implicitly_wait(DEFAULT_TIMEOUT)
        cls.wait = WebDriverWait(cls.driver, DEFAULT_TIMEOUT)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.driver.quit()
        finally:
            super().tearDownClass()

    def setUp(self):
        self.system = Entity.create(EntityType.SYSTEM)
        self.world = Entity.create(EntityType.WORLD)
        self.officer = make_officer()
        self.project = make_project("UI Test Farm")
        inject_project_fund(self.system, self.project, Decimal("5000.00"), self.officer)

    # ------------------------------------------------------------------
    # Failure artifacts: screenshot + HTML on failure
    # ------------------------------------------------------------------

    def _save_artifacts(self):
        test_id = getattr(self, "_testMethodName", "unknown")
        ts = time.strftime("%Y%m%d_%H%M%S")
        base = f"{type(self).__name__}_{test_id}_{ts}"
        try:
            self.driver.save_screenshot(str(SCREENSHOTS_DIR / f"{base}.png"))
            html = self.driver.page_source
            (SCREENSHOTS_DIR / f"{base}.html").write_text(html, encoding="utf-8")
        except Exception:  # never mask the original failure
            pass

    def tearDown(self):
        # Save failure artifacts for both failures and errors. Python 3.14's
        # unittest no longer exposes _outcome.errors, so read the TestResult.
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None)
        if result is not None:
            entries = (
                list(result.failures)
                + list(result.errors)
                + list(result.expectedFailures)
            )
            if any(err is not None for _test, err in entries):
                self._save_artifacts()
        super().tearDown()

    # ------------------------------------------------------------------
    # URL + navigation helpers
    # ------------------------------------------------------------------

    def absurl(self, name, *args):
        """Absolute URL for a route (live server + language prefix)."""
        return self.live_server_url + reverse(name, args=args)

    def goto(self, name, *args):
        self.driver.get(self.absurl(name, *args))
        return self

    def wait_for(self, predicate, description):
        try:
            self.wait.until(lambda d: predicate(d))
        except TimeoutException:
            snippet = ""
            try:
                snippet = self.driver.find_element(By.TAG_NAME, "body").text[:300]
            except Exception:
                pass
            self.fail(
                f"Timed out waiting for {description} "
                f"(url={self.driver.current_url}) body.text[:300]={snippet!r}"
            )

    def wait_for_url_contains(self, fragment):
        self.wait_for(
            lambda d: fragment in d.current_url, f"url containing {fragment!r}"
        )

    def assert_on_route(self, name):
        expected = reverse(name)
        self.assertTrue(
            expected in self.driver.current_url,
            f"expected to be on route {expected!r}, got {self.driver.current_url!r}",
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login_as_officer(self):
        """Drive the real login form (pins the AUTH contract, no session shortcut).

        Submits via the password field so the navbar language-switcher buttons
        (EN/AR — also type=submit, and earlier in the DOM) can never be hit.
        """
        self.goto("login")
        self.driver.find_element(By.NAME, "username").send_keys("officer")
        self.driver.find_element(By.NAME, "password").send_keys("testpass")
        self.driver.find_element(By.NAME, "password").submit()
        self.wait_for_url_contains("entities")
        return self

    # ------------------------------------------------------------------
    # Visible-response assertions (spec clause proxies)
    # ------------------------------------------------------------------

    def body_text(self):
        return self.driver.find_element(By.TAG_NAME, "body").text

    def assert_visible_text(self, text, msg=None):
        # Case-insensitive: CSS text-transform (e.g. text-uppercase) makes
        # Selenium return the computed "SOURCE FUND" even though the template
        # writes "Source Fund".
        needle = text.lower()
        self.wait_for(
            lambda d: needle in d.find_element(By.TAG_NAME, "body").text.lower(),
            f"visible text {text!r}",
        )
        return self

    def assert_absent(self, text):
        self.assertNotIn(
            text.lower(), self.body_text().lower(), f"unexpected text {text!r}"
        )

    def assert_flash_contains(self, text):
        alerts = self.driver.find_elements(By.CSS_SELECTOR, ".alert")
        joined = " ".join(a.text for a in alerts)
        self.assertIn(
            text, joined, f"no flash containing {text!r}; alerts={joined!r}"
        )

    def assert_fund_balance(self, entity, expected):
        """Open the entity's operation list and assert the visible balance badge."""
        self.goto("operation_list_view", entity.pk)
        self.assert_visible_text(f"{expected:.2f}")

    # ------------------------------------------------------------------
    # Form helpers
    # ------------------------------------------------------------------

    def fill(self, name, value):
        el = self.driver.find_element(By.NAME, name)
        try:
            el.clear()
        except Exception:
            # Some inputs (number/hidden) can refuse clear(); select-all then type.
            el.send_keys(Keys.CONTROL, "a")
        el.send_keys(str(value))
        return el

    def fill_date(self, name, value):
        """Set a ``<input type=date>`` via JS.

        Native ``send_keys`` on a date input is parsed in the browser's locale
        (MM/DD/YYYY), so an ISO ``YYYY-MM-DD`` string is rejected ("Enter a valid
        date"). Setting ``element.value`` directly keeps the ISO contract.
        """
        self.driver.execute_script(
            "var el=document.querySelector('input[name=%(name)s]');"
            "if(el){el.value=arguments[0];"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));}"
            % {"name": name},
            str(value),
        )
        return self

    def fill_amount(self, value, name="amount"):
        """Fill a formatter-managed amount input (visible + hidden name twin).

        AmountInputFormatter (amount-input-formatter.js) converts any
        ``input.amount-input`` into a visible text input (drops the name, keeps
        ``data-original-name``) plus a hidden input that keeps the original name for
        POST. Setting both via JS is deterministic — typing through the formatter's
        listener proved unreliable in headless Chrome.
        """
        self.driver.execute_script(
            "var hidden=document.querySelector('input[name=\"%(name)s\"]');"
            "var visible=document.querySelector("
            "'input[data-original-name=\"%(name)s\"]');"
            "if(visible){visible.value=arguments[0];"
            "visible.dispatchEvent(new Event('input',{bubbles:true}));"
            "visible.dispatchEvent(new Event('change',{bubbles:true}));}"
            "if(hidden){hidden.value=arguments[0];}" % {"name": name},
            str(value),
        )
        return self

    def select(self, name, value):
        """Select an option by value; falls back to a JS set for select2 fields."""
        try:
            Select(self.driver.find_element(By.NAME, name)).select_by_value(str(value))
        except Exception:
            self.driver.execute_script(
                "var sel=document.querySelector('select[name=%(name)s]');"
                "if(!sel) return;"
                "var opt=sel.querySelector('option[value=\"%(value)s\"]');"
                "if(opt){sel.value=opt.value;}"
                "sel.dispatchEvent(new Event('change',{bubbles:true}));"
                % {"name": name, "value": value}
            )
        return self

    def select_secondary_entity(self, entity):
        """Pick ``entity`` in the create form's secondary-entity dropdown."""
        return self.select("secondary_entity", entity.pk)

    def disable_html5_validation(self):
        """Let the browser POST even when a field is required/min-guarded, so the
        server-side validation (the spec clause) can be exercised."""
        self.driver.execute_script(
            "document.querySelectorAll('form').forEach(function(f){"
            "f.setAttribute('novalidate','');});"
        )
        return self

    def click_submit(self, button_text=None):
        """Click the submit button of the page's main form.

        Scoped to ``#main-content`` so the navbar's language-switcher (EN/AR) and
        logout forms — both earlier in the DOM and both type=submit — are never
        hit. Scrolls into view; falls back to a JS click when a fixed overlay
        (e.g. the flash-message container) intercepts the native click.
        """
        text_clause = (
            f" and contains(normalize-space(.), {button_text!r})" if button_text else ""
        )
        xpath = (
            "//main[@id='main-content']"
            "//form[not(contains(@action, 'setlang'))]"
            "//button[@type='submit'"
            f"{text_clause}]"
        )
        el = self.driver.find_element(By.XPATH, xpath)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});", el
        )
        try:
            el.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", el)
        return self

    def assert_no_element(self, css_selector):
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, css_selector)),
            0,
            f"expected no element matching {css_selector!r}",
        )

    def click_wizard_next(self):
        """Click the Purchase/Sale wizard's footer submit button.

        The wizard templates render the submit button *outside* the form element,
        linked to it via ``form="wizard-form"`` (``app_operation/{sale,purchase}_wizard.html``).
        ``click_submit`` cannot find it because it only looks inside ``<form>``.
        """
        xpath = (
            "//main[@id='main-content']"
            "//button[@type='submit'][@form='wizard-form']"
        )
        el = self.driver.find_element(By.XPATH, xpath)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'center'});", el
        )
        try:
            el.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", el)
        return self

    def goto_query(self, name, *args, **query):
        """Navigate to ``name`` (with args) plus a raw ``?k=v`` query string.

        The sale/purchase item forms require a ``product_id`` / ``template_id``
        query parameter that the plain ``goto`` helper cannot express.
        """
        qs = "&".join(f"{k}={v}" for k, v in query.items())
        url = self.absurl(name, *args) + (f"?{qs}" if qs else "")
        self.driver.get(url)
        return self

    # ------------------------------------------------------------------
    # Operation clause helpers
    # ------------------------------------------------------------------

    def create_one_shot(
        self, op_type, entity, amount, secondary=None, description="UI test"
    ):
        """Open the generic create form for a one-shot op and submit it.

        ``secondary`` (optional) is selected in the secondary-entity picker when the
        operation's post-role needs it (e.g. Project Funding, Internal Transfer).
        Assumes redirect to operation detail on success.
        """
        self.goto("operation_create_view", entity.pk, op_type)
        # The create form pre-fills `date` with today (server-side), which is
        # always covered by the entity's auto-created open period, so leave it.
        if secondary is not None:
            self.select_secondary_entity(secondary)
        self.fill_amount(f"{amount:.2f}")
        self.fill("description", description)
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self

    def reverse_operation(self, op, reason="UI test reversal"):
        self.goto("operation_reverse_view", op.pk)
        self.driver.find_element(By.NAME, "reversal_reason").send_keys(reason)
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self

    def reverse_transaction(self, tx, reason="UI transaction reversal"):
        """Reverse a single financial transaction (TransactionReverseView).

        Used to undo a standalone payment/collection before reversing the
        operation it belongs to (operations with explicit payments are guarded
        from operation-level reversal until their transactions are reversed).
        """
        self.goto("transaction_reverse_view", tx.pk)
        self.driver.find_element(By.NAME, "reversal_reason").send_keys(reason)
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self

    def record_payment(self, op, amount, note="UI payment"):
        """Record a payment (A6) on ``op`` via the standalone payment form."""
        self.goto("record_transaction_payment", op.pk)
        self.fill_amount(f"{amount:.2f}")
        self.fill("note", note)
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self

    def record_repayment(self, op, amount, note="UI repayment"):
        """Record a repayment (A7) on ``op`` via the standalone repayment form."""
        self.goto("record_transaction_repayment", op.pk)
        self.fill_amount(f"{amount:.2f}")
        self.fill("note", note)
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self
