from django.contrib import admin
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Keyword, Location,
                     ScrapingSetting, Pack, Price, CreditAction, KeywordLocationCombination, Favorite, AbstractTemplate,
                     Ad, GeneralSetting, SearchTerm, UserProfile)
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from datetime import datetime
import logging
from import_export import widgets


logger = logging.getLogger(__name__)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_verified']


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
    readonly_fields = ("generated_pdf", "thumbnail")
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
            'title', 'description', 'requirements', 'company_name', 'company_logo',
            'company_size', 'location', 'linkedin_profiles', 'employment_type',
            'original_url', 'salary_range', 'min_salary', 'max_salary',
            'benefits', 'skills_required', 'posted_date', 'expiration_date',
            'industry', 'job_type', 'job_id'
        ]
        export_order = fields
        skip_unknown = True
        skip_unchanged = True
        report_skipped = True
        import_id_fields = ("job_id",)

    def before_import_row(self, row, **kwargs):
        """
        Clean data before importing:
        - Convert empty strings to None for specific fields.
        - Convert 'posted_date' to a datetime object.
        - Handle row skipping logic for duplicates and outdated jobs.
        """
        # Fields that should convert empty strings to None
        nullable_fields = ['company_size', 'min_salary', 'max_salary']

        for field in nullable_fields:
            if row.get(field) == '':
                row[field] = None

        # Handle 'posted_date' - convert empty strings to None or parse valid date
        if 'posted_date' in row:
            if row['posted_date'] == '':
                row['posted_date'] = None
            else:
                try:
                    row['posted_date'] = datetime.strptime(row['posted_date'], "%Y-%m-%d").date()
                except ValueError:
                    logger.warning("Invalid date format for posted_date: %s", row['posted_date'])
                    row['posted_date'] = None

        # Handle 'expiration_date' - convert empty strings to None or parse valid date
        if 'expiration_date' in row:
            if row['expiration_date'] == '':
                row['expiration_date'] = None
            else:
                try:
                    row['expiration_date'] = datetime.strptime(row['expiration_date'], "%Y-%m-%d").date()
                except ValueError:
                    logger.warning("Invalid date format for expiration_date: %s", row['expiration_date'])
                    row['expiration_date'] = None

        # Handle missing job_id
        job_id = row.get('job_id')
        if not job_id:
            logger.warning("Skipping row with missing job_id: %s", row)
            return None

        # Skip duplicate job_id
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
            csv_posted_date = row.get('posted_date')
            if csv_posted_date and existing_job.posted_date:
                # Compare dates
                if csv_posted_date > existing_job.posted_date:
                    # Update fields for the existing job
                    for field in self.get_fields():
                        if field.attribute in row and field.attribute not in ['id', 'created_at', 'updated_at']:
                            setattr(existing_job, field.attribute, row.get(field.attribute))
                    existing_job.updated_at = datetime.now()
                    existing_job.save()
                    logger.info("Updated existing job: %s", existing_job)
                    return None  # Skip row after updating
                else:
                    logger.info("Skipping row, existing job is newer or equal: %s", existing_job)
                    return None

        return row  # Proceed with creating a new job


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


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ('title', 'description', 'original_url', 'is_active')
    search_fields = ('title', 'description', 'original_url')


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    list_display = ('job', 'cv', 'similarity_score', 'search_date')
    search_fields = ('cv__name', 'job__title')


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


@admin.register(GeneralSetting)
class GeneralSettingAdmin(admin.ModelAdmin):
    list_display = ['ads_per_page', 'max_recent_search_terms', 'last_updated']
    list_editable = ['ads_per_page', 'max_recent_search_terms']
    list_display_links = None
    help_texts = {"ads_per_page": "Set the number of ads displayed on each page."}


@admin.register(ScrapingSetting)
class ScrapingSettingAdmin(admin.ModelAdmin):
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


@admin.register(SearchTerm)
class SearchTermAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'term', 'is_active', 'last_searched_at']