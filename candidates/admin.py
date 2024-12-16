from django.contrib import admin
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Keyword, Location,
                     ScrapingSettings, Pack, Price, CreditAction, KeywordLocationCombination, Favorite, AbstractTemplate)
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from datetime import datetime
import logging
from import_export import widgets


logger = logging.getLogger(__name__)


@admin.register(AbstractTemplate)
class AbstractTemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'reference', 'image', 'created_at', 'updated_at']
    search_fields = ['name', 'reference']
    list_filter = ['created_at', 'updated_at']
    ordering = ['name']


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'language', 'abstract_template', 'get_cv', 'created_at', 'updated_at'
    ]
    search_fields = ['abstract_template__name', 'abstract_template__reference', 'language']
    list_filter = ['language', 'created_at', 'updated_at']
    autocomplete_fields = ['abstract_template']
    ordering = ['abstract_template__name', 'language']

    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }

    fieldsets = (
        (None, {
            'fields': ('abstract_template', 'language')
        }),
        ('Details', {
            'fields': (
                'company_logo', 'page', 'certifications', 'education', 'experience',
                'volunteering', 'interests', 'languages', 'projects', 'references',
                'skills', 'social', 'theme', 'personnel', 'typography'
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    readonly_fields = ['created_at', 'updated_at']

    def get_cv(self, obj):
        """Display the associated CV ID."""
        if hasattr(obj, 'cv'):
            return obj.cv.id  # Display the CV ID or any field you prefer
        return "No CV"

    get_cv.short_description = "CV ID"


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'get_username', 'get_email', 'phone', 'credits')
    search_fields = ('first_name', 'last_name', 'user__username', 'user__email')

    # Access the username through the related User model
    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'

    # Access the email through the related User model
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(CV)
class CVAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'cv_type', 'thumbnail', 'created_at', 'updated_at')
    search_fields = ('candidate__first_name', 'candidate__last_name')

    def delete_model(self, request, obj):
        if obj.template:
            obj.template.delete()
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Iterate through the queryset to delete associated templates
        for cv in queryset:
            if cv.template:
                cv.template.delete()  # Delete the associated template
        super().delete_queryset(request, queryset)


@admin.register(CVData)
class CVDataAdmin(admin.ModelAdmin):
    list_display = ['cv', 'title', 'name', 'email', 'phone']
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('cv__candidate__first_name', 'cv__candidate__last_name')


class NullableIntegerWidget(widgets.IntegerWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if value == '':
            return None
        return super().clean(value, row=row, *args, **kwargs)


class JobResource(resources.ModelResource):
    class Meta:
        model = Job
        fields = [
            'title', 'description', 'requirements', 'company_name',
            'company_size', 'location', 'linkedin_profiles', 'employment_type',
            'original_url', 'salary_range', 'min_salary', 'max_salary',
            'benefits', 'skills_required', 'posted_date', 'expiration_date',
            'industry', 'job_type', 'job_id'
        ]
        export_order = fields
        skip_unknown = True

    def before_import_row(self, row, **kwargs):
        """
        Decide if this row should be skipped or updated before importing.
        If we return None, the row will be skipped.
        """
        job_id = row.get('job_id')

        # Convert empty string in 'company_size' to None
        # so that it can be saved as NULL in the database.
        if 'company_size' in row and row['company_size'] == '':
            row['company_size'] = None

        # Skip rows with no job_id
        if not job_id:
            logger.warning("Skipping row with missing job_id: %s", row)
            return None

        # Check if a job with the same ID exists (duplicate)
        if Job.objects.filter(job_id=job_id).exists():
            logger.info("Skipping duplicate job_id: %s", job_id)
            return None

        # Check for duplicate jobs with (title, company_name, location)
        existing_job = Job.objects.filter(
            title=row.get('title'),
            company_name=row.get('company_name'),
            location=row.get('location')
        ).first()

        if existing_job:
            csv_posted_date_str = row.get('posted_date')
            if csv_posted_date_str and existing_job.posted_date:
                csv_posted_date = datetime.strptime(csv_posted_date_str, "%Y-%m-%d").date()
                # If CSV posted_date is more recent, update the existing job
                if csv_posted_date > existing_job.posted_date:
                    for field in self.get_fields():
                        if field.attribute in row and field.attribute not in ['id', 'created_at', 'updated_at']:
                            setattr(existing_job, field.attribute, row.get(field.attribute))
                    existing_job.updated_at = datetime.now()
                    existing_job.save()
                    logger.info("Updated existing job: %s", existing_job)
                    # After updating, skip creating a new entry
                    return None
                else:
                    # CSV posted_date is the same or older, skip row
                    logger.info("Skipping row, existing job is newer or equal: %s", existing_job)
                    return None
            else:
                # If no posted_date or not newer, skip
                logger.info("Skipping row, no posted_date or not newer: %s", existing_job)
                return None

        # If no reason to skip, return the row as-is
        return row

    # No need to override import_row now, since skipping and updating logic
    # is handled in before_import_row(). If before_import_row() returns row,
    # django-import-export will attempt to create a new instance.


@admin.register(Job)
class JobAdmin(ImportExportModelAdmin):
    resource_class = JobResource
    list_display = ('id', 'title', 'company_name', 'location', 'employment_type', 'job_type', 'posted_date')
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('title', 'company_name', 'location')

    def has_import_permission(self, request):
        return True


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    list_display = ('job', 'candidate', 'similarity_score', 'search_date')
    search_fields = ('candidate__first_name', 'job__title')


@admin.register(CreditPurchase)
class CreditPurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'credits_purchased', 'timestamp')
    search_fields = ('candidate__first_name',)


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ['keyword']
    fields = ['keyword']
    search_fields = ['keyword__keyword']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['location']
    fields = ['location']
    search_fields = ['location__location']


@admin.register(ScrapingSettings)
class ScrapingSettingsAdmin(admin.ModelAdmin):
    list_display = ('num_jobs_to_scrape', 'is_scraping')


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    search_fields = ['name']
    list_filter = ['is_active']


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ['pack', 'credits', 'price']
    search_fields = ['pack__name', 'credits']
    list_filter = ['pack']


@admin.register(CreditAction)
class CreditActionAdmin(admin.ModelAdmin):
    list_display = ['action_name', 'credit_cost']
    search_fields = ['action_name']


@admin.register(KeywordLocationCombination)
class KeywordLocationCombinationAdmin(admin.ModelAdmin):
    list_display = ['keyword', 'location', 'is_scraped']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'job', 'created_at']

