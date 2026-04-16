from django.db import models
from django.utils.translation import gettext_lazy as _


class InvoiceItemAdjustmentType(models.TextChoices):
    PURCHASE_ITEM_INCREASE = "PUR_ITEM_INC", _("Purchase Item: Increase")
    PURCHASE_ITEM_DECREASE = "PUR_ITEM_DEC", _("Purchase Item: Decrease")
    SALE_ITEM_INCREASE = "SALE_ITEM_INC", _("Sale Item: Increase")
    SALE_ITEM_DECREASE = "SALE_ITEM_DEC", _("Sale Item: Decrease")
