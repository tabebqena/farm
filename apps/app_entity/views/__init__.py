"""Public view namespace for the entity app.

Re-exports the entity list/detail, person & project create/edit, project setup
wizard, stakeholder, contact-info and category-relation views so they can be
imported directly from ``apps.app_entity.views``.
"""

from .add_contact_info import AddContactInfoView
from .add_stakeholder import (
    AddClientView,
    AddShareholderView,
    AddVendorView,
    AddWorkerView,
)
from .category import (
    CategoryBulkAssignView,
    CategoryRelationDetailView,
    CategoryRelationEditView,
)
from .edit_contact_info import EditContactInfoView
from .edit_stakeholder import EditStakeholderView
from .entity_detail import EntityDetailView
from .entity_list import EntityListView
from .person_create import PersonCreateView
from .person_edit import PersonEditView
from .project_edit import ProjectEditView
from .project_setup_wizard import project_setup_wizard_view

__all__ = [
    "EntityListView",
    "EntityDetailView",
    "PersonCreateView",
    "PersonEditView",
    "ProjectEditView",
    "project_setup_wizard_view",
    "AddContactInfoView",
    "EditContactInfoView",
    "AddClientView",
    "AddShareholderView",
    "AddWorkerView",
    "AddVendorView",
    "EditStakeholderView",
    "CategoryRelationEditView",
    "CategoryRelationDetailView",
    "CategoryBulkAssignView",
]
