from django.db import models


class AdjustmentEffect(models.TextChoices):
    INCREASE = "INCREASE", "Increase"
    DECREASE = "DECREASE", "Decrease"
