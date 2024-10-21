from django.contrib import admin
from .models import Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase
from django.db import models
from django_json_widget.widgets import JSONEditorWidget
from django_celery_results.models import TaskResult


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
    list_display = ('candidate', 'created_at', 'updated_at')
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
    list_display = ('title', 'company_name', 'location', 'employment_type', 'job_type', 'posted_date')
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    search_fields = ('title', 'company_name', 'location')


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    list_display = ('job', 'candidate', 'similarity_score', 'search_date')
    search_fields = ('candidate__first_name', 'job__title')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'amount', 'currency', 'payment_method', 'status', 'timestamp')
    search_fields = ('candidate__first_name', 'transaction_id')


@admin.register(CreditPurchase)
class CreditPurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'credits_purchased', 'timestamp')
    search_fields = ('candidate__first_name',)

