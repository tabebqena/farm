"""UI tests for cross-cutting behaviour (root redirect, 404, language switch)."""
from selenium.webdriver.common.by import By

from ui_tests.base import UiTestCase


class CrosscuttingUiTests(UiTestCase):
    """GEN clauses from ai-plans/manual-test-plan.md."""

    def test_root_redirects_to_entity_list(self):
        """GEN-01: the app root redirects to the entity list."""
        self.login_as_officer()
        self.driver.get(self.live_server_url + "/en/")
        self.wait_for_url_contains("entities")

    def test_missing_entity_renders_404_page(self):
        """GEN-03: a non-existent entity shows the custom 404 page."""
        self.login_as_officer()
        self.driver.get(self.live_server_url + "/en/entities/99999999/")
        # The custom handler404 renders a page (not an empty/broken response).
        body = self.driver.find_element(By.TAG_NAME, "body").text
        self.assertTrue(len(body) > 0, "404 page rendered empty")
        self.assertNotIn("OperationalError", body)
        self.assertNotIn("Traceback", body)

    def test_language_switch_to_arabic(self):
        """GEN-02: the AR button switches the UI language (URL gains /ar/)."""
        self.login_as_officer()
        self.driver.find_element(By.CSS_SELECTOR, "button[value='ar']").click()
        self.wait_for_url_contains("/ar/")
