from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import InvoiceItem, Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(username="officer1", is_staff=True):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=is_staff
    )


def make_entity(
    entity_type,
    name="TestEntity",
    is_vendor=False,
    is_client=False,
):
    e = Entity.create(entity_type, name=name, is_vendor=is_vendor, is_client=is_client)

    return e


def make_project_entity(name="TestEntity", is_vendor=False, is_client=False):
    return make_entity(EntityType.PROJECT, name, is_vendor, is_client)


def make_person_entity(name="TestEntity", is_vendor=False, is_client=False):
    return make_entity(EntityType.PERSON, name, is_vendor, is_client)


def make_operation(
    source,
    destination,
    officer,
    proxy_class: type = PurchaseOperation,
    operation_type=OperationType.PURCHASE,
    amount=Decimal("100.00"),
):
    """
    Bypass BaseModel.full_clean() (which requires proxy-level methods like
    payment_source_fund) by calling Django's base Model.save() directly,
    skipping all custom mixin save() chains.
    """
    op = proxy_class.objects.create(
        source=source,
        destination=destination,
        officer=officer,
        operation_type=operation_type,
        amount=amount,
        date=date.today(),
        deletable=False,
    )
    # op.save()
    return op


def make_product_template(name="Calves"):
    return ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.ANIMAL,
        sub_category="Cattle",
        tracking_mode=ProductTemplate.TrackingMode.BATCH,
        default_unit="Head",
    )


def make_invoice_item(
    operation,
    template,
    quantity=Decimal("5.00"),
    unit_price=Decimal("100.00"),
):
    return InvoiceItem.objects.create(
        operation=operation,
        product=template,
        quantity=quantity,
        unit_price=unit_price,
    )


def make_product(template, unit_price=Decimal("100.00"), quantity=1):
    return Product.objects.create(
        product_template=template,
        unit_price=unit_price,
        quantity=quantity,
    )
