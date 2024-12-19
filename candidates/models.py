from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Candidate(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)  # New field for country
    credits = models.IntegerField(default=0)
    # num_jobs_to_scrape = models.IntegerField(default=10)
    # scrape_interval = models.IntegerField(default=1)
    # scrape_unit = models.CharField(
    #     max_length=10,
    #     choices=[('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks')],
    #     default='hours'
    # )
    # last_scrape_time = models.DateTimeField(blank=True, null=True)
    # is_scraping = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Notification(models.Model):
    candidate = models.ForeignKey('Candidate', on_delete=models.CASCADE, related_name='notifications')
    job = models.ForeignKey('Job', on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.TextField()
    is_viewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.candidate.user.username}: {self.message[:30]}"


class CreditOrder(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    credits = models.PositiveIntegerField()
    order_id = models.CharField(max_length=100, unique=True)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.order_id} for {self.credits} credits"


class AbstractTemplate(models.Model):
    name = models.CharField(max_length=255)
    reference = models.CharField(max_length=255, blank=True, null=True)
    image = models.ImageField(upload_to='template_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}"


class Template(models.Model):
    language = models.CharField(max_length=10, choices=[('en', 'English'), ('fr', 'French')], default='en')
    abstract_template = models.ForeignKey(
        AbstractTemplate,
        on_delete=models.CASCADE,
        related_name="templates",
        blank=True,
        null=True,
    )
    company_logo = models.JSONField(default=dict)
    page = models.JSONField(default=dict)
    certifications = models.JSONField(default=dict)
    education = models.JSONField(default=dict)
    experience = models.JSONField(default=dict)
    volunteering = models.JSONField(default=dict)
    interests = models.JSONField(default=dict)
    languages = models.JSONField(default=dict)
    projects = models.JSONField(default=dict)
    references = models.JSONField(default=dict)
    skills = models.JSONField(default=dict)
    social = models.JSONField(default=dict)
    theme = models.JSONField(default=dict)
    personnel = models.JSONField(default=dict)
    typography = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Template {self.abstract_template.name} ({self.language})"

    @property
    def template(self):
        return self.abstract_template.name

    @property
    def reference(self):
        return self.abstract_template.reference

    @property
    def identity(self):
        return self.abstract_template.reference


class CV(models.Model):
    BASE = 'base'
    TAILORED = 'tailored'

    CV_TYPE_CHOICES = [
        (BASE, 'Base CV'),
        (TAILORED, 'Tailored CV'),
    ]

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='cvs')
    original_file = models.FileField(upload_to='Cvs/original/', blank=True, null=True)
    template = models.OneToOneField(Template, on_delete=models.SET_NULL, null=True, blank=True)
    generated_pdf = models.FileField(upload_to='Cvs/pdf/', blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    cv_type = models.CharField(max_length=10, choices=CV_TYPE_CHOICES, default=BASE)
    job = models.ForeignKey('Job', on_delete=models.CASCADE, null=True, blank=True, related_name='tailored_cvs')
    thumbnail = models.ImageField(upload_to='Cvs/thumbnails/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_cv_type_display()} for {self.candidate.first_name} {self.candidate.last_name}"

    @property
    def is_base_cv(self):
        return self.cv_type == self.BASE

    @property
    def is_tailored_cv(self):
        return self.cv_type == self.TAILORED


class CVData(models.Model):
    cv = models.OneToOneField(CV, on_delete=models.CASCADE, related_name='cv_data')
    title = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    yoe = models.CharField(max_length=100, blank=True, null=True)
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
        return f"Data for {self.cv.get_cv_type_display()} of {self.cv.candidate.first_name} {self.cv.candidate.last_name}"


class Job(models.Model):
    title = models.CharField(max_length=255, blank=True, null=True)
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
    original_url = models.CharField(max_length=1000)

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
    job_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
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


class Keyword(models.Model):
    keyword = models.CharField(max_length=100, unique=True)
    is_scraped = models.BooleanField(default=False)

    def __str__(self):
        return self.keyword


class Location(models.Model):
    location = models.CharField(max_length=100, unique=True)
    is_scraped = models.BooleanField(default=False)

    def __str__(self):
        return self.location


class KeywordLocationCombination(models.Model):
    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    is_scraped = models.BooleanField(default=False)

    class Meta:
        unique_together = ('keyword', 'location')

    def __str__(self):
        return f"{self.keyword.keyword} + {self.location.location}"


class ScrapingSettings(models.Model):
    num_jobs_to_scrape = models.IntegerField(default=100)
    is_scraping = models.BooleanField(default=False)

    def __str__(self):
        return f"Scraping Settings: {self.num_jobs_to_scrape} jobs"

    def save(self, *args, **kwargs):
        if not self.pk and ScrapingSettings.objects.exists():
            # This below line will render error by breaking page, you will see
            raise ValidationError(
                "There can be only one instance of settings, you can not add another"
            )
            return None

        return super(ScrapingSettings, self).save(*args, **kwargs)


class Pack(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g., "Basic Pack", "Advanced Pack"
    description = models.TextField(blank=True, null=True)  # Optional description
    is_active = models.BooleanField(default=True)  # Indicates if the pack is active
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Price(models.Model):
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name='prices')  # Link to the Pack
    credits = models.PositiveIntegerField()  # Number of credits
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price in USD or other currency

    class Meta:
        unique_together = ('pack', 'credits')  # Ensure no duplicate credit options in the same pack

    def __str__(self):
        return f"{self.credits} credits for ${self.price} ({self.pack.name})"


class CreditAction(models.Model):
    action_name = models.CharField(max_length=100, unique=True)
    credit_cost = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.action_name} - {self.credit_cost} credits"


class Favorite(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="favorites")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('candidate', 'job')  # Ensure no duplicate favorites


