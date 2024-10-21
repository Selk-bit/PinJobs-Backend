from rest_framework import serializers
from .models import Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase
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


class CVDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CVData
        fields = '__all__'


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'


class JobSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSearch
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class CreditPurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditPurchase
        fields = '__all__'
