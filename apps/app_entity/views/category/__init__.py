"""Public view namespace for category-relation views.

Re-exports the category bulk-assign, relation-detail and relation-edit views so
they can be imported from ``apps.app_entity.views.category``.
"""

from .category_bulk_assign import CategoryBulkAssignView
from .category_relation_detail import CategoryRelationDetailView
from .category_relation_edit import CategoryRelationEditView

__all__ = [
    "CategoryRelationEditView",
    "CategoryRelationDetailView",
    "CategoryBulkAssignView",
]
