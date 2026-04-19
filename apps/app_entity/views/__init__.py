from .add_contact_info import add_contact_info_view
from .add_stakeholder import (add_client_view, add_shareholder_view,
                              add_vendor_view, add_worker_view)
from .edit_contact_info import edit_contact_info_view
from .edit_stakeholder import edit_stakeholder_view
from .entity_detail import entity_detail_view
from .entity_list import entity_list_view
from .person_create import person_create_view
from .person_edit import person_edit_view
from .project_create import project_create_view
from .project_edit import project_edit_view
from .project_setup_wizard import project_setup_wizard_view

__all__ = [
    "entity_list_view",
    "entity_detail_view",
    "person_create_view",
    "project_create_view",
    "person_edit_view",
    "project_edit_view",
    "project_setup_wizard_view",
    "add_contact_info_view",
    "edit_contact_info_view",
    "add_client_view",
    "add_shareholder_view",
    "add_worker_view",
    "add_vendor_view",
    "edit_stakeholder_view",
]
