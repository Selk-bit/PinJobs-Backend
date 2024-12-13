from rest_framework import serializers
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Location, Keyword,
                     Price, Pack, AbstractTemplate)
from django.contrib.auth.models import User
from rest_framework.response import Response


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class CandidateSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)  # Nested serializer for the User data

    class Meta:
        model = Candidate
        fields = ['id', 'first_name', 'last_name', 'phone', 'age', 'city', 'country', 'credits', 'user']


class TemplateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="abstract_template.name", read_only=True)
    reference = serializers.CharField(source="abstract_template.reference", read_only=True)
    language = serializers.CharField(source="abstract_template.language", read_only=True)
    templateData = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = [
            "id", "name", "language", "reference", "identity", "templateData", "created_at", "updated_at"
        ]

    def get_templateData(self, obj):
        """
        Return the nested structure for `templateData`, mimicking the old serializer.
        """
        return {
            "identity": obj.abstract_template.reference,
            "template": obj.abstract_template.name,
            "company_logo": obj.company_logo,
            "page": obj.page,
            "certifications": obj.certifications,
            "education": obj.education,
            "experience": obj.experience,
            "volunteering": obj.volunteering,
            "interests": obj.interests,
            "languages": obj.languages,
            "projects": obj.projects,
            "references": obj.references,
            "skills": obj.skills,
            "social": obj.social,
            "theme": obj.theme,
            "personnel": obj.personnel,
            "typography": obj.typography,
        }


class AbstractTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbstractTemplate
        fields = ["id", "name", "reference", "image", "created_at", "updated_at"]


class CVDataSerializer(serializers.ModelSerializer):
    cv_id = serializers.IntegerField(source='cv.id', read_only=True)
    title = serializers.SerializerMethodField()

    class Meta:
        model = CVData
        fields = [
            "cv_id", "title", "name", "email", "phone", "age", "city",
            "work", "educations", "languages", "skills", "interests",
            "social", "certifications", "projects", "volunteering",
            "references", "headline", "summary",
        ]

    def get_title(self, obj):
        return obj.headline

    def to_internal_value(self, data):
        # Convert empty strings to None for nullable fields
        for field in self.fields:
            if data.get(field) == "":
                data[field] = None
        return super().to_internal_value(data)


class JobSerializer(serializers.ModelSerializer):
    similarity_score = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = ["id", "title", "description", "requirements", "company_name", "company_size", "location", "linkedin_profiles", "employment_type", "original_url", "min_salary", "max_salary", "benefits", "skills_required", "posted_date", "industry", "job_type", "similarity_score"]

    def get_similarity_score(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            candidate = getattr(request.user, 'candidate', None)
            if candidate:
                job_search = JobSearch.objects.filter(job=obj, candidate=candidate).first()
                if job_search:
                    return job_search.similarity_score
        return None


class CVSerializer(serializers.ModelSerializer):
    job = JobSerializer()
    cv_data = CVDataSerializer()
    thumbnail = serializers.ImageField(read_only=True)
    name = serializers.SerializerMethodField()
    template = serializers.SerializerMethodField()

    class Meta:
        model = CV
        fields = ['id', "name", 'original_file', 'generated_pdf', 'thumbnail', 'cv_data', 'job', 'template', 'created_at', 'updated_at']

    def get_name(self, obj):
        if obj.cv_type == CV.BASE:
            # For base CVs, use cv_data title
            title = obj.cv_data.title if obj.cv_data and obj.cv_data.title else "Untitled"
            return f"{title} - Base CV"
        elif obj.cv_type == CV.TAILORED:
            # For tailored CVs, use job title and company name
            if obj.job:
                job_title = obj.job.title if obj.job.title else "Untitled Job"
                company_name = obj.job.company_name if obj.job.company_name else "Unknown Company"
                return f"{job_title} - {company_name}"
        return "Untitled"

    def get_template(self, obj):
        # Serialize the associated template, if it exists
        if obj.template:
            return TemplateSerializer(obj.template).data
        return None


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


class KeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Keyword
        fields = '__all__'


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'


class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = ['credits', 'price']


class PackSerializer(serializers.ModelSerializer):
    prices = PriceSerializer(many=True)

    class Meta:
        model = Pack
        fields = ['id', 'name', 'description', 'is_active', 'prices']