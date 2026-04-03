from django.db import models

from apps.app_base.models import BaseModel


class ProductEvaluation(BaseModel):
    product = models.ForeignKey(
        "aap_inventory.Product", on_delete=models.CASCADE, related_name="evaluations"
    )

    price = models.DecimalField(max_digits=15, decimal_places=2)
    # Metadata for Bonuses
    evaluator = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.SET_NULL,
        null=True,
    )
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
