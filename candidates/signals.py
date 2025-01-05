from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Keyword, Location, KeywordLocationCombination, CV, Template, AbstractTemplate, CVData
from .constants import DEFAULT_TEMPLATE_DATA
from .utils import generate_cv_pdf


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


@receiver(post_save, sender=CV)
def create_default_template(sender, instance, created, **kwargs):
    """
    Signal to create a default template for newly created CVs if none exists,
    and only if the abstract template "sydney" is available.
    """
    if created and not instance.name:
        try:
            if instance.cv_type == CV.BASE:
                title = instance.cv_data.title if hasattr(instance, 'cv_data') and instance.cv_data.title else "Untitled"
                instance.name = f"{title} - Base CV"
            elif instance.cv_type == CV.TAILORED:
                if instance.job:
                    job_title = instance.job.title if instance.job.title else "Untitled Job"
                    company_name = instance.job.company_name if instance.job.company_name else "Unknown Company"
                    instance.name = f"{job_title} - {company_name}"
                else:
                    instance.name = "Untitled"
            else:
                instance.name = "Untitled"

            instance.save(update_fields=["name"])
        except Exception as e:
            instance.name = "Untitled"
            instance.save(update_fields=["name"])
            print(f"Error setting CV name: {e}")

    if created and not instance.template:
        try:
            # Retrieve the abstract template "sydney"
            abstract_template = AbstractTemplate.objects.get(name="sydney")
        except AbstractTemplate.DoesNotExist:
            # If "sydney" does not exist, do nothing
            return

        # Create the default template
        template = Template.objects.create(
            abstract_template=abstract_template,
            language=DEFAULT_TEMPLATE_DATA['language'],
            company_logo=DEFAULT_TEMPLATE_DATA['company_logo'],
            page=DEFAULT_TEMPLATE_DATA['page'],
            certifications=DEFAULT_TEMPLATE_DATA['certifications'],
            education=DEFAULT_TEMPLATE_DATA['education'],
            experience=DEFAULT_TEMPLATE_DATA['experience'],
            volunteering=DEFAULT_TEMPLATE_DATA['volunteering'],
            interests=DEFAULT_TEMPLATE_DATA['interests'],
            languages=DEFAULT_TEMPLATE_DATA['languages'],
            projects=DEFAULT_TEMPLATE_DATA['projects'],
            references=DEFAULT_TEMPLATE_DATA['references'],
            skills=DEFAULT_TEMPLATE_DATA['skills'],
            social=DEFAULT_TEMPLATE_DATA['social'],
            theme=DEFAULT_TEMPLATE_DATA['theme'],
            personnel=DEFAULT_TEMPLATE_DATA['personnel'],
            typography=DEFAULT_TEMPLATE_DATA['typography'],
        )

        # Associate the template with the CV
        instance.template = template
        instance.save()


@receiver(post_save, sender=CVData)
def update_cv_name_after_cvdata_save(sender, instance, created, **kwargs):
    """
    Update the CV name after the related CVData is created or updated.
    """
    try:
        cv = instance.cv  # Access the related CV instance
        if not cv.name or "Untitled" in cv.name:
            if cv.cv_type == CV.BASE:
                if not instance.title:
                    instance.title = instance.headline if instance.headline else "Untitled"
                cv.name = f"{instance.title} - Base CV"
                cv.save(update_fields=["name"])
                instance.save()
    except Exception as e:
        print(f"Error updating CV name after CVData save: {e}")


@receiver(post_save, sender=CVData)
@receiver(post_save, sender=Template)
def handle_cv_update(sender, instance, **kwargs):
    """
    Signal triggered when CVData or Template is created/updated.
    """
    # Determine the associated CV instance
    if sender == CVData:
        cv = instance.cv  # Direct relation from CVData
    elif sender == Template:
        try:
            cv = CV.objects.get(template=instance)  # Find CV using the template
        except CV.DoesNotExist:
            cv = None

    # Generate PDF if both cv_data and template exist
    if cv and cv.cv_data and cv.cv_data.name and cv.template:
        generate_cv_pdf(cv)