"""Tests for the AddStakeholderView and its role-based subclasses.

Covers GET eligibility filtering, POST creation, duplicate handling,
validation failures, and 404 paths. These tests pin the behaviour of the
refactored (method-split) view.
"""

from django.contrib.messages import get_messages
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder
from apps.app_entity.views.add_stakeholder import AddStakeholderView, _role_filter
from apps.app_inventory.tests.general import make_user


class UnknownRoleView(AddStakeholderView):
    """Subclass with an unrecognised role to guard the fallback branch."""

    role_type = "mystery"


class AddStakeholderViewTest(TestCase):
    """Test the add-stakeholder flow across roles."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_stakeholder", is_staff=True)
        self.client.login(username="officer_stakeholder", password="testpass")

        # Host project must be internal for _load_parent to accept it, and is
        # vendor-capable so the GET dropdown must exclude it by id.
        self.project = Entity.create(
            EntityType.PROJECT,
            name="Stakeholder Project",
            is_internal=True,
            is_vendor=True,
        )
        self.vendor = Entity.create(
            EntityType.PERSON, name="Vendor Co", is_vendor=True, active=True
        )
        self.client_entity = Entity.create(
            EntityType.PERSON, name="Client Co", is_client=True, active=True
        )
        self.worker = Entity.create(
            EntityType.PERSON, name="Worker Jane", is_worker=True, active=True
        )
        self.shareholder = Entity.create(
            EntityType.PERSON, name="Shareholder John", is_shareholder=True, active=True
        )
        self.non_vendor = Entity.create(
            EntityType.PERSON, name="Plain Person", active=True
        )

    # ------------------------------------------------------------------ #
    # _role_filter unit checks
    # ------------------------------------------------------------------ #

    def test_role_filter_maps_known_roles(self):
        """Known roles map to their eligibility filter kwargs."""
        self.assertEqual(
            _role_filter("worker"), {"is_worker": True, "active": True}
        )
        self.assertEqual(
            _role_filter("shareholder"), {"is_shareholder": True, "active": True}
        )
        self.assertEqual(
            _role_filter("vendor"), {"is_vendor": True, "active": True}
        )
        self.assertEqual(
            _role_filter("client"), {"is_client": True, "active": True}
        )

    def test_role_filter_unknown_role_returns_none(self):
        """Unknown roles return None so the view renders an empty dropdown."""
        self.assertIsNone(_role_filter("mystery"))

    # ------------------------------------------------------------------ #
    # GET
    # ------------------------------------------------------------------ #

    def test_get_renders_only_eligible_vendors(self):
        """GET for vendor shows only active vendor entities, host excluded."""
        url = reverse("add_vendor", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app_entity/stakeholder_form.html")
        entities = list(response.context["entities"])
        self.assertIn(self.vendor, entities)
        self.assertNotIn(self.non_vendor, entities)
        # The host project itself is excluded even though it is vendor-capable.
        self.assertNotIn(self.project, entities)
        self.assertEqual(response.context["role_type"], "vendor")
        self.assertEqual(response.context["role_name"], "Vendor")
        self.assertEqual(response.context["project_entity"], self.project)

    def test_get_filters_each_role(self):
        """GET filters eligible entities per role."""
        cases = [
            ("add_client", self.client_entity),
            ("add_worker", self.worker),
            ("add_shareholder", self.shareholder),
        ]
        for url_name, eligible in cases:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, kwargs={"pk": self.project.pk})
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                entities = list(response.context["entities"])
                self.assertIn(eligible, entities)
                self.assertNotIn(self.non_vendor, entities)

    def test_get_unknown_role_renders_empty_dropdown(self):
        """An unknown role falls back to an empty eligible-entity list."""
        factory = RequestFactory()
        request = factory.get(
            reverse("add_vendor", kwargs={"pk": self.project.pk})
        )
        request.user = self.officer
        response = UnknownRoleView.as_view()(request, pk=self.project.pk)

        self.assertEqual(response.status_code, 200)
        # With no eligible entities the dropdown must not list any candidate.
        content = response.content.decode()
        self.assertNotIn(self.vendor.name, content)
        self.assertNotIn(self.non_vendor.name, content)

    # ------------------------------------------------------------------ #
    # POST
    # ------------------------------------------------------------------ #

    def test_post_creates_stakeholder_and_redirects(self):
        """A valid POST creates an active stakeholder and redirects."""
        url = reverse("add_vendor", kwargs={"pk": self.project.pk})
        response = self.client.post(url, {"target_entity": self.vendor.pk})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("entity_detail", kwargs={"pk": self.project.pk}),
        )
        stakeholder = Stakeholder.objects.get(
            parent=self.project, target=self.vendor, role="vendor"
        )
        self.assertTrue(stakeholder.active)

    def test_post_duplicate_does_not_create_second_row(self):
        """Re-submitting the same target reuses the existing stakeholder."""
        url = reverse("add_vendor", kwargs={"pk": self.project.pk})
        self.client.post(url, {"target_entity": self.vendor.pk})
        response = self.client.post(url, {"target_entity": self.vendor.pk})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Stakeholder.objects.filter(
                parent=self.project, target=self.vendor, role="vendor"
            ).count(),
            1,
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Successfully added" in str(message) for message in messages)
        )

    def test_post_non_person_worker_rerenders_with_error(self):
        """A non-Person target cannot be assigned as a worker."""
        non_person = Entity.create(EntityType.PROJECT, name="Not a Person", active=True)
        url = reverse("add_worker", kwargs={"pk": self.project.pk})
        response = self.client.post(url, {"target_entity": non_person.pk})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app_entity/stakeholder_form.html")
        self.assertEqual(
            Stakeholder.objects.filter(parent=self.project, role="worker").count(), 0
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Configuration Error" in str(message) for message in messages)
        )

    def test_post_non_vendor_target_rerenders_with_error(self):
        """A target not configured as a vendor is rejected."""
        url = reverse("add_vendor", kwargs={"pk": self.project.pk})
        response = self.client.post(url, {"target_entity": self.non_vendor.pk})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app_entity/stakeholder_form.html")
        self.assertEqual(
            Stakeholder.objects.filter(parent=self.project, role="vendor").count(), 0
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Configuration Error" in str(message) for message in messages)
        )

    def test_post_non_internal_parent_returns_404(self):
        """A non-internal parent project is rejected with a 404."""
        external = Entity.create(EntityType.PROJECT, name="External Project")
        url = reverse("add_vendor", kwargs={"pk": external.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_post_missing_target_returns_404(self):
        """A missing/inactive target entity returns a 404."""
        url = reverse("add_vendor", kwargs={"pk": self.project.pk})
        response = self.client.post(url, {"target_entity": 99999})

        self.assertEqual(response.status_code, 404)
