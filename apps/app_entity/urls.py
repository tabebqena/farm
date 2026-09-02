"""URL routing for the entity app.

Covers entity list/detail, person and project create/edit, the multi-step
project setup wizard, stakeholder and contact-info management, and category
relation views.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.EntityListView.as_view(), name="entity_list"),
    path("person/add/", views.PersonCreateView.as_view(), name="person_create"),
    path("person/edit/<int:pk>", views.PersonEditView.as_view(), name="person_edit"),
    path("project/edit/<int:pk>", views.ProjectEditView.as_view(), name="project_edit"),
    path("project/setup/", views.project_setup_wizard_view, name="project_create"),
    path(
        "project/<int:entity_pk>/setup/<int:step>/",
        views.project_setup_wizard_view,
        name="project_setup_step",
    ),
    path("<int:pk>/", views.EntityDetailView.as_view(), name="entity_detail"),
    path(
        "<int:entity_id>/contact/add/",
        views.AddContactInfoView.as_view(),
        name="add_contact_info",
    ),
    path(
        "contact/<int:pk>/edit/",
        views.EditContactInfoView.as_view(),
        name="edit_contact_info",
    ),
    path(
        "project/<int:pk>/add-vendor/",
        views.AddVendorView.as_view(),
        name="add_vendor",
    ),
    path(
        "project/<int:pk>/add-client/",
        views.AddClientView.as_view(),
        name="add_client",
    ),
    path(
        "project/<int:pk>/add-worker/",
        views.AddWorkerView.as_view(),
        name="add_worker",
    ),
    path(
        "project/<int:pk>/add-shareholder/",
        views.AddShareholderView.as_view(),
        name="add_shareholder",
    ),
    path(
        "stakeholder/<int:pk>/edit/",
        views.EditStakeholderView.as_view(),
        name="edit_stakeholder",
    ),
    # Categories
    path(
        "category/edit/<int:pk>",
        views.CategoryRelationEditView.as_view(),
        name="category_relation_edit_view",
    ),
    path(
        "category/detail/<int:pk>",
        views.CategoryRelationDetailView.as_view(),
        name="category_relation_detail_view",
    ),
    path(
        "<int:parent_entity_id>/category/bulk-assign/",
        views.CategoryBulkAssignView.as_view(),
        name="category_bulk_assign_view",
    ),
]
