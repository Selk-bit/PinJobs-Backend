from django.contrib import admin
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Modele, Keyword, Location,
                     ScrapingSettings, Pack, Price, CreditAction, KeywordLocationCombination, Favorite)
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from django_celery_results.models import TaskResult


@admin.register(Modele)
class ModeleAdmin(admin.ModelAdmin):
    list_display = ['id', 'identity', 'template']
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ['identity', 'template']
    list_filter = ['template']


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'language', 'reference']
    search_fields = ['name', 'reference', 'language']
    list_filter = ['language']


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
    list_display = ('candidate', 'cv_type', 'created_at', 'updated_at')
    search_fields = ('candidate__first_name', 'candidate__last_name')


@admin.register(CVData)
class CVDataAdmin(admin.ModelAdmin):
    list_display = ['cv', 'title', 'name', 'email', 'phone']
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('cv__candidate__first_name', 'cv__candidate__last_name')


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'company_name', 'location', 'employment_type', 'job_type', 'posted_date')
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('title', 'company_name', 'location')


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

