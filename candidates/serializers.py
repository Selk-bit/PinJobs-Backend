from rest_framework import serializers
from .models import Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Modele, Template
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class CandidateSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)  # Nested serializer for the User data

    class Meta:
        model = Candidate
        fields = ['id', 'first_name', 'last_name', 'phone', 'age', 'city', 'country', 'credits', 'user', 'num_jobs_to_scrape', 'scrape_interval', 'scrape_unit']


class CVSerializer(serializers.ModelSerializer):
    class Meta:
        model = CV
        fields = ['id', 'candidate', 'original_file', 'generated_html', 'generated_pdf', 'created_at', 'updated_at']


class ModeleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modele
        fields = [
            "identity", "template", "company_logo", "page", "certifications", "education",
            "experience", "volunteering", "interests", "languages", "projects",
            "references", "skills", "social", "theme", "personnel", "typography"
        ]


class TemplateSerializer(serializers.ModelSerializer):
    templateData = ModeleSerializer()

    class Meta:
        model = Template
        fields = ["id", "name", "language", "reference", "templateData"]


class CVDataSerializer(serializers.ModelSerializer):
    cv_id = serializers.IntegerField(source='cv.id', read_only=True)

    class Meta:
        model = CVData
        fields = [
            "cv_id", "title", "name", "email", "phone", "age", "city",
            "work", "educations", "languages", "skills", "interests",
            "social", "certifications", "projects", "volunteering",
            "references", "headline", "summary",
        ]

    def to_internal_value(self, data):
        # Convert empty strings to None for nullable fields
        for field in self.fields:
            if data.get(field) == "":
                data[field] = None
        return super().to_internal_value(data)


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "title", "description", "requirements", "company_name", "company_size", "location", "linkedin_profiles", "employment_type", "original_url", "min_salary", "max_salary", "benefits", "skills_required", "posted_date", "industry", "job_type"]


class JobSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSearch
        fields = ["similarity_score", "search_date", "status"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class CreditPurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditPurchase
        fields = '__all__'
