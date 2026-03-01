from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.pipeline.services import create_default_pipeline_for_organization
from apps.users.models import Organization


@receiver(post_save, sender=Organization)
def ensure_default_pipeline_for_organization(sender, instance, created, **kwargs):
    if created:
        create_default_pipeline_for_organization(instance)
