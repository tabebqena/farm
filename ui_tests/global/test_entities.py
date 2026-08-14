"""UI tests for the entity list/detail views (ENT clauses)."""
from decimal import Decimal

from ui_tests.base import UiTestCase, make_person, inject_person_fund


class EntitiesUiTests(UiTestCase):
    """ENT clauses from ai-plans/manual-test-plan.md."""

    def test_entity_list_shows_entity(self):
        """ENT-01: the entity list renders and includes created entities."""
        person = make_person("Listed Person")
        self.login_as_officer()
        self.goto("entity_list")
        self.assert_visible_text("Listed Person")

    def test_entity_detail_shows_name_and_balance(self):
        """ENT-10: the detail page shows the name and the current fund balance."""
        person = make_person("Detail Person")
        inject_person_fund(self.world, person, Decimal("250.00"), self.officer)
        self.login_as_officer()
        self.goto("entity_detail", person.pk)
        self.assert_visible_text("Detail Person")
        self.assert_visible_text("250.00")
