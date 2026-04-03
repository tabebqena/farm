from django.db import models


class Category(models.Model):
    class Nature(models.TextChoices):
        ANIMAL = "ANIMAL", "Livestock Asset"
        FEED = "FEED", "Consumable"
        MEDICINE = "MEDICINE", "Biological"
        PRODUCT = "PRODUCT", "Production Output"

    name = models.CharField(max_length=100)  # e.g., "Fattening Calves"
    nature = models.CharField(choices=Nature.choices, max_length=20)
    default_unit = models.CharField(max_length=20)  # e.g., "Head", "Kg"
    requires_individual_tag = models.BooleanField(default=False)


class Product(models.Model):
    class TrackingMode(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual (Tag ID)"
        BATCH = "BATCH", "Batch/Group"
        COMMODITY = "COMMODITY", "Quantity (Weight/Volume)"

    name = models.CharField(max_length=255)  # e.g. "Angus Cow #405" or "Batch #12"
    category = models.ForeignKey(Category, on_delete=models.PROTECT)  # e.g. "Cattle"
    tracking_mode = models.CharField(choices=TrackingMode.choices)

    # Livestock-specific fields
    # birth_date = models.DateField(null=True)
    # initial_weight = models.DecimalField(...)
