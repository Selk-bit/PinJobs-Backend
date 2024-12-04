from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Keyword, Location, KeywordLocationCombination, CV, CVData


@receiver(post_save, sender=Keyword)
def create_combinations_for_new_keyword(sender, instance, **kwargs):
    locations = Location.objects.all()
    for location in locations:
        KeywordLocationCombination.objects.get_or_create(keyword=instance, location=location)


@receiver(post_save, sender=Location)
def create_combinations_for_new_location(sender, instance, **kwargs):
    keywords = Keyword.objects.all()
    for keyword in keywords:
        KeywordLocationCombination.objects.get_or_create(keyword=keyword, location=instance)


@receiver(pre_save, sender=CV)
def enforce_single_base_cv(sender, instance, **kwargs):
    if instance.cv_type == CV.BASE:
        CV.objects.filter(candidate=instance.candidate, cv_type=CV.BASE).exclude(id=instance.id).delete()