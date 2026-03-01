from django.db import models


class AnalyticsPlaceholder(models.Model):
    class Meta:
        managed = False
        verbose_name = "Analytics placeholder"
