from django.contrib import admin
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Keyword, Location,
                     ScrapingSettings, Pack, Price, CreditAction, KeywordLocationCombination, Favorite, AbstractTemplate)
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from datetime import datetime


@admin.register(AbstractTemplate)
class AbstractTemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'reference', 'image', 'created_at', 'updated_at']
    search_fields = ['name', 'reference']
    list_filter = ['created_at', 'updated_at']
    ordering = ['name']


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'language', 'abstract_template', 'created_at', 'updated_at'
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


class JobResource(resources.ModelResource):
    class Meta:
        model = Job
        fields = [
            'title', 'description', 'requirements', 'company_name',
            'company_size', 'location', 'linkedin_profiles', 'employment_type',
            'original_url', 'salary_range', 'min_salary', 'max_salary',
            'benefits', 'skills_required', 'posted_date', 'expiration_date',
            'industry', 'job_type'
        ]
        export_order = fields

    def import_row(self, row, instance_loader, **kwargs):
        """
        Custom import logic:
        - If a job with the same ID exists, skip it.
        - If a job with the same title, location, and company_name exists:
          - Compare posted_date, and if the CSV job's posted_date is more recent,
            update the existing job with the CSV job's data.
        """
        # Check if a job with the same ID exists
        if Job.objects.filter(job_id=row.get('job_id')).exists():
            return None  # Skip the row

        # Check if a job with the same title, location, and company_name exists
        existing_job = Job.objects.filter(
            title=row.get('title'),
            company_name=row.get('company_name'),
            location=row.get('location')
        ).first()

        if existing_job:
            # Compare posted_date
            csv_posted_date = row.get('posted_date')
            if csv_posted_date and existing_job.posted_date:
                csv_posted_date = datetime.strptime(csv_posted_date, "%Y-%m-%d").date()
                if csv_posted_date > existing_job.posted_date:
                    # Update the existing job with CSV data
                    for field in self.get_fields():
                        if field.attribute in row and field.attribute != 'id':  # Skip the ID field
                            setattr(existing_job, field.attribute, row.get(field.attribute))
                    existing_job.save()
            return None  # Skip the row, as it's already handled

        # If no existing job matches, proceed with creating a new job
        return super().import_row(row, instance_loader, **kwargs)


@admin.register(Job)
class JobAdmin(ImportExportModelAdmin):
    list_display = ('id', 'title', 'company_name', 'location', 'employment_type', 'job_type', 'posted_date')
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('title', 'company_name', 'location')

    def has_import_permission(self, request):
        return True


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    resource_class = JobResource
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

