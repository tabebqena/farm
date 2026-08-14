"""UI tests for the authentication contract (login / wrong password / next)."""
from django.urls import reverse
from selenium.webdriver.common.by import By

from ui_tests.base import UiTestCase, make_person


class AuthUiTests(UiTestCase):
    """AUTH clauses from ai-plans/manual-test-plan.md."""

    def test_login_wrong_password_shows_error(self):
        """AUTH-02: wrong credentials re-render the login page with the error."""
        self.goto("login")
        self.driver.find_element(By.NAME, "username").send_keys("officer")
        self.driver.find_element(By.NAME, "password").send_keys("wrongpass")
        self.driver.find_element(By.NAME, "password").submit()
        self.assert_visible_text("didn't match")
        self.assertTrue("login" in self.driver.current_url)

    def test_login_next_redirect(self):
        """AUTH-04: after login the user returns to the original requested page."""
        person = make_person("Redirect Person")
        target = reverse("operation_list_view", args=[person.pk])
        self.driver.get(self.live_server_url + "/en/login/?next=" + target)
        self.driver.find_element(By.NAME, "username").send_keys("officer")
        self.driver.find_element(By.NAME, "password").send_keys("testpass")
        self.driver.find_element(By.NAME, "password").submit()
        self.wait_for_url_contains("list")
