"""URL routing for the audit/provenance app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.ActivityListView.as_view(), name="audit_activity"),
    path(
        "trace/<int:pk>/",
        views.TraceDetailView.as_view(),
        name="audit_trace_detail",
    ),
    path(
        "record/<str:app_label>/<str:model>/<str:object_id>/",
        views.RecordHistoryView.as_view(),
        name="audit_record_history",
    ),
]
