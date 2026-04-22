from django.urls import path

from . import views

urlpatterns = [
    # path("", RedirectView.as_view(pattern_name="entity_list", permanent=False)),
    path("", views.entity_list_view, name="entity_list"),
    path("person/add/", views.person_create_view, name="person_create"),
    path("person/edit/<int:pk>", views.person_edit_view, name="person_edit"),
    # path("project/add/", views.project_create_view, name="project_create"),
    path("project/edit/<int:pk>", views.project_edit_view, name="project_edit"),
    # path("project/setup/", views.project_setup_wizard_view, name="project_setup"),
    # JUST TO Test
    path("project/setup/", views.project_setup_wizard_view, name="project_create"),
    path(
        "project/<int:entity_pk>/setup/<int:step>/",
        views.project_setup_wizard_view,
        name="project_setup_step",
    ),
    path("<int:pk>/", views.entity_detail_view, name="entity_detail"),
    path(
        "<int:entity_id>/contact/add/",
        views.add_contact_info_view,
        name="add_contact_info",
    ),
    path(
        "contact/<int:pk>/edit/", views.edit_contact_info_view, name="edit_contact_info"
    ),
    path("project/<int:pk>/add-vendor/", views.add_vendor_view, name="add_vendor"),
    path("project/<int:pk>/add-client/", views.add_client_view, name="add_client"),
    path("project/<int:pk>/add-worker/", views.add_worker_view, name="add_worker"),
    path(
        "project/<int:pk>/add-shareholder/",
        views.add_shareholder_view,
        name="add_shareholder",
    ),
    path(
        "stakeholder/<int:pk>/edit/",
        views.edit_stakeholder_view,
        name="edit_stakeholder",
    ),
    # Categories
    path(
        "category/edit/<int:pk>",
        views.category_relation_edit_view,
        name="category_relation_edit_view",
    ),
    path(
        "category/detail/<int:pk>",
        views.category_relation_detail_view,
        name="category_relation_detail_view",
    ),
    path(
        "<int:parent_entity_id>/category/bulk-assign/",
        views.category_bulk_assign_view,
        name="category_bulk_assign_view",
    ),
]
