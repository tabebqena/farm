"""Public namespace for operation-creation views.

Re-exports the generic :class:`OperationCreateView`, the birth / death and
capital-valuation create views, and the purchase / sale wizard view functions so
they can be imported from ``apps.app_operation.views.create_operation``.
"""

from .base import OperationCreateView
from .create_birth_view import BirthCreateView
from .create_death_view import (
    DeathCreateView,
)
from .evaluation import EvaluationCreateView
from .purchase_wizard import (
    cancel_purchase_wizard_view,
    purchase_add_item_view,
    purchase_delete_item_view,
    purchase_invoice_view,
    purchase_select_template_view,
    purchase_submit_view,
    purchase_wizard_view,
)
from .sale_wizard import (
    cancel_sale_wizard_view,
    sale_add_item_view,
    sale_delete_item_view,
    sale_invoice_view,
    sale_select_product_view,
    sale_submit_view,
    sale_wizard_view,
)

__all__ = [
    "OperationCreateView",
    "BirthCreateView",
    "DeathCreateView",
    "cancel_sale_wizard_view",
    "sale_add_item_view",
    "sale_delete_item_view",
    "sale_invoice_view",
    "sale_select_product_view",
    "sale_submit_view",
    "sale_wizard_view",
    "cancel_purchase_wizard_view",
    "purchase_add_item_view",
    "purchase_delete_item_view",
    "purchase_invoice_view",
    "purchase_select_template_view",
    "purchase_submit_view",
    "purchase_wizard_view",
    "EvaluationCreateView",
]
