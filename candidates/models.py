from django.db import models
from django.contrib.auth.models import User


class Candidate(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)  # New field for country
    credits = models.IntegerField(default=0)
    num_jobs_to_scrape = models.IntegerField(default=10)
    scrape_interval = models.IntegerField(default=1)  # Number of intervals (e.g., every 1 hour)
    scrape_unit = models.CharField(
        max_length=10,
        choices=[('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks')],
        default='hours'
    )
    last_scrape_time = models.DateTimeField(blank=True, null=True)
    is_scraping = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"




class CV(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE)
    original_file = models.FileField(upload_to='cvs/original/', blank=True, null=True)
    generated_html = models.TextField(blank=True, null=True)
    generated_pdf = models.FileField(upload_to='cvs/pdf/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CV for {self.candidate.first_name} {self.candidate.last_name}"


class CVData(models.Model):
    cv = models.ForeignKey(CV, on_delete=models.CASCADE, related_name='cv_data')
    title = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    work = models.JSONField(blank=True, null=True)
    educations = models.JSONField(blank=True, null=True)
    languages = models.JSONField(blank=True, null=True)
    skills = models.JSONField(blank=True, null=True)
    interests = models.JSONField(blank=True, null=True)
    social = models.JSONField(blank=True, null=True)
    certifications = models.JSONField(blank=True, null=True)
    projects = models.JSONField(blank=True, null=True)
    volunteering = models.JSONField(blank=True, null=True)
    references = models.JSONField(blank=True, null=True)
    headline = models.CharField(max_length=255, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Data for CV of {self.cv.candidate.first_name} {self.cv.candidate.last_name}"


class Job(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.JSONField(blank=True, null=True)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    company_size = models.IntegerField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    linkedin_profiles = models.JSONField(blank=True, null=True)

    EMPLOYMENT_TYPE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('on-site', 'On-site'),
    ]
    employment_type = models.CharField(
        max_length=50,
        choices=EMPLOYMENT_TYPE_CHOICES,
        blank=True,
        null=True
    )
    original_url = models.URLField()

    salary_range = models.CharField(max_length=100, blank=True, null=True)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    benefits = models.JSONField(blank=True, null=True)
    skills_required = models.JSONField(blank=True, null=True)
    posted_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)

    JOB_TYPE_CHOICES = [
        ('full-time', 'Full-time'),
        ('part-time', 'Part-time'),
        ('contract', 'Contract'),
        ('freelance', 'Freelance'),
        ('CDD', 'CDD (Fixed-term)'),
        ('CDI', 'CDI (Indefinite-term)'),
        ('other', 'Other'),
    ]
    job_type = models.CharField(
        max_length=50,
        choices=JOB_TYPE_CHOICES,
        default='full-time'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} at {self.company_name}"

class JobSearch(models.Model):
    candidate = models.ForeignKey('Candidate', on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    similarity_score = models.FloatField()
    search_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ('matched', 'Matched'),
            ('applied', 'Applied')
        ],
        default='matched'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Job search for {self.candidate} - {self.job.title}"


class Payment(models.Model):
    candidate = models.ForeignKey('Candidate', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ('paypal', 'PayPal'),
            ('stripe', 'Stripe')
        ],
        default='stripe'
    )
    transaction_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('refunded', 'Refunded')
        ],
        default='pending'
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.transaction_id} - {self.status}"


class CreditPurchase(models.Model):
    candidate = models.ForeignKey('Candidate', on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    credits_purchased = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.credits_purchased} credits for {self.candidate}"