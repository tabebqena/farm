from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="entity_list", permanent=False)),
    path("entities/", views.entity_list_view, name="entity_list"),
    path("entities/person/add/", views.person_create_view, name="person_create"),
    path("entities/person/edit/<int:pk>", views.person_edit_view, name="person_edit"),
    path("entities/project/add/", views.project_create_view, name="project_create"),
    path(
        "entities/project/edit/<int:pk>", views.project_edit_view, name="project_edit"
    ),
    path(
        "entities/category/add/<int:parent_entity_id>",
        views.category_create_view,
        name="category_create",
    ),
    path(
        "entities/category/edit/<int:pk>",
        views.category_edit_view,
        name="category_edit",
    ),
    path("entities/<int:pk>/", views.entity_detail_view, name="entity_detail"),
    path(
        "entity/<int:entity_id>/contact/add/",
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
]
