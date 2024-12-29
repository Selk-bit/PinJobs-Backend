from rest_framework import viewsets
from .models import (Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, CreditOrder,
                     Pack, Price, Favorite, AbstractTemplate)
from .serializers import (CandidateSerializer, CVSerializer, CVDataSerializer, JobSerializer, JobSearchSerializer,
                          PaymentSerializer, CreditPurchaseSerializer, TemplateSerializer, PackSerializer,
                          AbstractTemplateSerializer)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
import requests
from django.core.files.storage import default_storage
from django.conf import settings
import os
from .utils import (get_gemini_response, deduct_credits, has_sufficient_credits, construct_only_score_job_prompt,
                    construct_similarity_prompt)
import json
from .tasks import run_scraping_task
from django.contrib.auth import authenticate
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.contrib.auth import update_session_auth_hash
import django_filters
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from datetime import datetime
from .utils import (paypal_client, is_valid_job_url, fetch_job_description, construct_tailored_job_prompt,
                    construct_single_job_prompt, construct_candidate_profile, extract_job_id)
from paypalcheckoutsdk.orders import OrdersCreateRequest, OrdersCaptureRequest
from django.db import transaction
from rest_framework.generics import ListAPIView, RetrieveAPIView
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework import serializers
from django.http import FileResponse, Http404
import httpx
from asgiref.sync import sync_to_async
import aiofiles
from .requests import AsyncRequest
from django.http import HttpRequest
from rest_framework.request import Request
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


class CandidateViewSet(viewsets.ModelViewSet):
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer


class CVViewSet(viewsets.ModelViewSet):
    queryset = CV.objects.all()
    serializer_class = CVSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure only the authenticated user can access their CV
        user = self.request.user
        return CV.objects.filter(candidate__user=user)


class CVDataViewSet(viewsets.ModelViewSet):
    queryset = CVData.objects.all()
    serializer_class = CVDataSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure only the authenticated user can access their CV data
        user = self.request.user
        return CVData.objects.filter(cv__candidate__user=user)


class JobViewSet(viewsets.ModelViewSet):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def filter_jobs(self, request):
        candidate_id = request.query_params.get('candidate_id')
        job_type = request.query_params.get('job_type')
        employment_type = request.query_params.get('employment_type')
        location = request.query_params.get('location')

        # Filter jobs based on the provided parameters
        queryset = Job.objects.all()
        if candidate_id:
            candidate = Candidate.objects.get(id=candidate_id)
            # Additional logic to filter based on candidate's profile can be added here
        if job_type:
            queryset = queryset.filter(job_type=job_type)
        if employment_type:
            queryset = queryset.filter(employment_type=employment_type)
        if location:
            queryset = queryset.filter(location__icontains=location)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def candidate_jobs(self, request, pk=None):
        candidate = Candidate.objects.get(pk=pk)
        job_searches = JobSearch.objects.filter(candidate=candidate)
        serializer = JobSearchSerializer(job_searches, many=True)
        return Response(serializer.data)


class JobSearchViewSet(viewsets.ModelViewSet):
    queryset = JobSearch.objects.all()
    serializer_class = JobSearchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure only the authenticated user can access their job searches
        user = self.request.user
        return JobSearch.objects.filter(candidate__user=user)


class JobFilter(django_filters.FilterSet):
    description = django_filters.CharFilter(field_name="description", lookup_expr='icontains')
    company_name = django_filters.CharFilter(field_name="company_name", lookup_expr='icontains')
    requirements = django_filters.CharFilter(field_name="requirements", lookup_expr='icontains')
    location = django_filters.CharFilter(field_name="location", lookup_expr='icontains')
    industry = django_filters.CharFilter(field_name="industry", lookup_expr='icontains')
    employment_type = django_filters.ChoiceFilter(choices=Job.EMPLOYMENT_TYPE_CHOICES)
    job_type = django_filters.ChoiceFilter(choices=Job.JOB_TYPE_CHOICES)

    # New filters for min and max salary
    min_salary = django_filters.NumberFilter(field_name="min_salary", lookup_expr='gte')
    max_salary = django_filters.NumberFilter(field_name="max_salary", lookup_expr='lte')

    # Date filters that parse the specific date format
    posted_date_range_after = django_filters.CharFilter(method='filter_posted_date_after')
    posted_date_range_before = django_filters.CharFilter(method='filter_posted_date_before')

    skills = django_filters.CharFilter(method='filter_by_skills')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Job
        fields = ['description', 'company_name', 'requirements', 'location', 'industry', 'employment_type',
                  'job_type', 'min_salary', 'max_salary', 'skills', 'search', 'posted_date_range_after', 'posted_date_range_before']


    def parse_date(self, date_str):
        try:
            # Remove the timezone in parentheses, e.g., "(GMT+01:00)"
            date_str = date_str.split(" (")[0]
            # Parse the date without the timezone description
            return datetime.strptime(date_str, '%a %b %d %Y %H:%M:%S GMT%z')
        except ValueError:
            return None

    def filter_posted_date_after(self, queryset, name, value):
        date_after = self.parse_date(value)
        if date_after:
            return queryset.filter(posted_date__gte=date_after.date())
        return queryset  # Ignore if parsing fails

    def filter_posted_date_before(self, queryset, name, value):
        date_before = self.parse_date(value)
        if date_before:
            return queryset.filter(posted_date__lte=date_before.date())
        return queryset  # Ignore if parsing fails

    def filter_by_skills(self, queryset, name, value):
        skills = [skill.strip().lower() for skill in value.split(',')]
        for skill in skills:
            queryset = queryset.filter(Q(skills_required__icontains=skill))
        return queryset

    def filter_search(self, queryset, name, value):
        value = value.strip().lower()
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(company_name__icontains=value) |
            Q(requirements__icontains=value) |
            Q(benefits__icontains=value)
        )


class CandidateJobsView(APIView):
    permission_classes = [IsAuthenticated]

    class CustomPagination(PageNumberPagination):
        page_size = 5
        page_size_query_param = 'page_size'
        max_page_size = 100

    @swagger_auto_schema(
        operation_description="Retrieve a list of jobs with optional filters and similarity scores "
                              "for the authenticated candidate.",
        manual_parameters=[
            openapi.Parameter('description', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job description (contains).'),
            openapi.Parameter('company_name', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by company name (contains).'),
            openapi.Parameter('requirements', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job requirements (contains).'),
            openapi.Parameter('location', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job location (contains).'),
            openapi.Parameter('industry', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job industry (contains).'),
            openapi.Parameter('employment_type', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by employment type (choices: remote, hybrid, on-site).'),
            openapi.Parameter('job_type', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job type (choices: full-time, part-time, contract, freelance, CDD, CDI, other).'),
            openapi.Parameter('min_salary', openapi.IN_QUERY, type=openapi.TYPE_NUMBER, description='Filter by minimum salary (greater than or equal).'),
            openapi.Parameter('max_salary', openapi.IN_QUERY, type=openapi.TYPE_NUMBER, description='Filter by maximum salary (less than or equal).'),
            openapi.Parameter('posted_date_range_after', openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME, description='Filter jobs posted after this date.'),
            openapi.Parameter('posted_date_range_before', openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME, description='Filter jobs posted before this date.'),
            openapi.Parameter('skills', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by required skills (comma-separated).'),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search across title, description, company name, requirements, and benefits.'),
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page number.'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Number of items per page.'),
        ],
        responses={200: JobSerializer(many=True)},
        security=[{'Bearer': []}]
    )
    def get(self, request):
        # Get the authenticated candidate
        candidate = request.user.candidate

        # Get the filter params from request
        filters = request.query_params
        # Apply filters for the Job model using the JobFilter
        job_filter = JobFilter(filters, queryset=Job.objects.all())
        jobs = job_filter.qs

        # Get all JobSearches for the candidate
        job_searches = JobSearch.objects.filter(candidate=candidate)
        # job_search_map = {job_search.job_id: job_search.similarity_score for job_search in job_searches}

        # Serialize jobs with similarity score
        results = []
        for job in jobs:
            job_data = JobSerializer(job, context={'request': request}).data
            # Add similarity score if the candidate has a JobSearch for the job
            # job_data['similarity_score'] = job_search_map.get(job.id, None)
            results.append(job_data)

        # Apply pagination
        paginator = self.CustomPagination()
        paginated_results = paginator.paginate_queryset(results, request)

        return paginator.get_paginated_response(paginated_results)


class JobDetailView(RetrieveAPIView):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve a single job by ID, including similarity score and favorite status.",
        responses={200: JobSerializer()},
        security=[{'Bearer': []}]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CandidateFavoriteJobsView(APIView):
    permission_classes = [IsAuthenticated]

    class CustomPagination(PageNumberPagination):
        page_size = 5
        page_size_query_param = 'page_size'
        max_page_size = 100

    @swagger_auto_schema(
        operation_description="Get the list of favorite jobs for the authenticated candidate.",
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER),
            openapi.Parameter('page_size', openapi.IN_QUERY, description="Number of items per page", type=openapi.TYPE_INTEGER),
        ],
        responses={200: JobSerializer(many=True)}
    )
    def get(self, request):
        # Get the authenticated candidate
        candidate = request.user.candidate

        # Get favorite jobs for the candidate
        favorite_jobs = Favorite.objects.filter(candidate=candidate).select_related('job')
        jobs = [fav.job for fav in favorite_jobs]

        # Get all JobSearches for the candidate
        job_searches = JobSearch.objects.filter(candidate=candidate)
        # job_search_map = {job_search.job_id: job_search.similarity_score for job_search in job_searches}

        # Serialize jobs with similarity score
        results = []
        for job in jobs:
            job_data = JobSerializer(job, context={'request': request}).data
            # Add similarity score if the candidate has a JobSearch for the job
            # job_data['similarity_score'] = job_search_map.get(job.id, None)
            results.append(job_data)

        # Apply pagination
        paginator = self.CustomPagination()
        paginated_results = paginator.paginate_queryset(results, request)

        return paginator.get_paginated_response(paginated_results)


    @swagger_auto_schema(
        operation_description="Add a job to the candidate's favorites.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['job_id'],
            properties={
                'job_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the job to favorite'),
            },
        ),
        responses={
            201: openapi.Response(description='Job added to favorites.'),
            200: openapi.Response(description='Job is already in favorites.'),
            400: openapi.Response(description='Bad request.'),
            404: openapi.Response(description='Job not found.'),
        },
    )
    def post(self, request):
        candidate = request.user.candidate
        job_id = request.data.get('job_id')

        if not job_id:
            return Response({"error": "Job ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        job = Job.objects.filter(id=job_id).first()
        if not job:
            return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        if candidate.favorites.count() >= 10:
            return Response({"error": "You can only add up to 10 favorite jobs."}, status=status.HTTP_400_BAD_REQUEST)

        favorite, created = Favorite.objects.get_or_create(candidate=candidate, job=job)
        if created:
            return Response({"detail": "Job added to favorites."}, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "Job is already in favorites."}, status=status.HTTP_200_OK)


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure only the authenticated user can access their payments
        user = self.request.user
        return Payment.objects.filter(candidate__user=user)


class CreditPurchaseViewSet(viewsets.ModelViewSet):
    queryset = CreditPurchase.objects.all()
    serializer_class = CreditPurchaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure only the authenticated user can access their credit purchases
        user = self.request.user
        return CreditPurchase.objects.filter(candidate__user=user)


class SignUpView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Register a new user and create a candidate profile.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['username', 'password'],
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username for the new user'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password for the new user'),
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='Email address'),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING, description='First name'),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING, description='Last name'),
                'phone': openapi.Schema(type=openapi.TYPE_STRING, description='Phone number'),
                'age': openapi.Schema(type=openapi.TYPE_INTEGER, description='Age'),
                'city': openapi.Schema(type=openapi.TYPE_STRING, description='City'),
            },
        ),
        responses={
            201: CandidateSerializer(),
            400: openapi.Response(description='Bad Request')
        }
    )
    def post(self, request):
        data = request.data
        try:
            # Create User object
            user = User.objects.create_user(
                username=data['username'],
                password=data['password'],
                email=data.get('email', '')
            )

            # Create Candidate object linked to the User
            candidate = Candidate.objects.create(
                user=user,  # Associate the User with the Candidate
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                phone=data.get('phone', ''),
                age=data.get('age', None),
                city=data.get('city', '')
            )

            serializer = CandidateSerializer(candidate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Authenticate a user and return JWT tokens.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['identifier', 'password'],
            properties={
                'identifier': openapi.Schema(type=openapi.TYPE_STRING, description='Username or email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password'),
            },
        ),
        responses={
            200: openapi.Response(
                description='Login successful',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'refresh': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token'),
                        'access': openapi.Schema(type=openapi.TYPE_STRING, description='Access token'),
                    }
                )
            ),
            401: openapi.Response(description='Invalid credentials'),
        }
    )
    def post(self, request):
        identifier = request.data.get('identifier')
        password = request.data.get('password')

        # Check if identifier is an email or username
        try:
            validate_email(identifier)
            is_email = True
        except ValidationError:
            is_email = False

        if is_email:
            # Try to get user by email
            try:
                user_obj = User.objects.get(email=identifier)
                username = user_obj.username
            except User.DoesNotExist:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            # If not an email, treat it as a username
            username = identifier

        # Authenticate with either the username or the email-found username
        user = authenticate(username=username, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Logout the authenticated user by blacklisting the token.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['access'],
            properties={
                'access': openapi.Schema(type=openapi.TYPE_STRING, description='Access token to blacklist'),
            },
        ),
        responses={
            205: openapi.Response(description='Successfully logged out'),
            400: openapi.Response(description='Bad Request'),
        }
    )
    def post(self, request):
        try:
            # Get the access token from the request
            access_token = request.data.get("access")

            if not access_token:
                return Response({"error": "Access token is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Create an AccessToken instance and blacklist it
            token = AccessToken(access_token)
            token.blacklist()

            return Response({"detail": "Successfully logged out"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve the authenticated user's profile.",
        responses={200: CandidateSerializer()}
    )
    def get(self, request):
        # Retrieve current user profile
        user = request.user
        candidate = get_object_or_404(Candidate, user=user)
        serializer = CandidateSerializer(candidate)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Update the authenticated user's profile.",
        request_body=CandidateSerializer,
        responses={200: CandidateSerializer(), 400: openapi.Response(description='Bad Request')}
    )
    def put(self, request):
        # Update current user profile
        user = request.user
        candidate = get_object_or_404(Candidate, user=user)
        serializer = CandidateSerializer(candidate, data=request.data, partial=False)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Partially update the authenticated user's profile.",
        request_body=CandidateSerializer,
        responses={200: CandidateSerializer(), 400: openapi.Response(description='Bad Request')}
    )
    def patch(self, request):
        # Partially update current user profile
        user = request.user
        candidate = get_object_or_404(Candidate, user=user)
        serializer = CandidateSerializer(candidate, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Change the authenticated user's password.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['old_password', 'new_password', 'confirm_password'],
            properties={
                'old_password': openapi.Schema(type=openapi.TYPE_STRING, description='Current password'),
                'new_password': openapi.Schema(type=openapi.TYPE_STRING, description='New password'),
                'confirm_password': openapi.Schema(type=openapi.TYPE_STRING, description='Confirm new password'),
            },
        ),
        responses={
            200: openapi.Response(description='Password updated successfully'),
            400: openapi.Response(description='Bad Request'),
        }
    )
    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not user.check_password(old_password):
            return Response({"error": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

        if old_password == new_password:
            return Response({"error": "New password cannot be the same as the old password"}, status=status.HTTP_400_BAD_REQUEST)

        # Update the password and maintain the session
        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)  # Important to keep the user logged in after changing the password

        return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)


class CVDataView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve the CV data for the authenticated user.",
        responses={200: CVDataSerializer()}
    )
    def get(self, request):
        # Get the authenticated candidate
        candidate = request.user.candidate

        # Retrieve the CVData for the candidate's base CV
        try:
            base_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
            # cv_data = base_cv.cv_data
            serializer = CVSerializer(base_cv)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CV.DoesNotExist:
            return Response({"error": "Base CV not found for the candidate"}, status=status.HTTP_404_NOT_FOUND)
        except CVData.DoesNotExist:
            return Response({"error": "CVData not found for the base CV"}, status=status.HTTP_404_NOT_FOUND)


    def handle_cv_data_update(self, cv, cv_data, partial):
        try:
            cv_data_instance = CVData.objects.get(cv=cv)
        except CVData.DoesNotExist:
            cv_data_instance = CVData(cv=cv)

        serializer = CVDataSerializer(cv_data_instance, data=cv_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

    def handle_template_update(self, cv, template_data, partial):
        template_name = template_data.get("templateData", {}).get("template")
        if not template_name:
            raise serializers.ValidationError({"error": "Template name is required."})

        try:
            abstract_template = AbstractTemplate.objects.get(name=template_name)
        except AbstractTemplate.DoesNotExist:
            raise serializers.ValidationError({"error": f"AbstractTemplate '{template_name}' not found."})

        # Remove unwanted keys
        template_data["templateData"].pop("identity", None)
        template_data["templateData"].pop("template", None)

        template, created = Template.objects.update_or_create(
            id=cv.template.id if cv.template else None,
            defaults={
                'abstract_template': abstract_template,
                'language': template_data.get('language', 'en'),
                **template_data.get("templateData", {})
            }
        )
        cv.template = template
        cv.save()

    @swagger_auto_schema(
        operation_description="Update the CV data and template for the authenticated user.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="CV name"),
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Base CV or AbstractTemplate not found."),
        },
    )
    def put(self, request):
        candidate = request.user.candidate
        required_keys = {"name", "cv_data", "template"}

        if not required_keys.issubset(request.data.keys()):
            return Response({"error": f"All fields {required_keys} are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            base_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
        except CV.DoesNotExist:
            return Response({"error": "Base CV not found for the candidate"}, status=status.HTTP_404_NOT_FOUND)

        base_cv.name = request.data["name"]
        base_cv.save(update_fields=["name"])

        self.handle_cv_data_update(base_cv, request.data["cv_data"], partial=False)
        self.handle_template_update(base_cv, request.data["template"], partial=False)

        return Response(CVSerializer(base_cv).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Partially Update the CV data and template for the authenticated user.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="CV name"),
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Base CV or AbstractTemplate not found."),
        },
    )
    def patch(self, request):
        candidate = request.user.candidate
        allowed_keys = {"name", "cv_data", "template"}

        if not set(request.data.keys()).intersection(allowed_keys):
            return Response({"error": f"At least one of {allowed_keys} is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            base_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
        except CV.DoesNotExist:
            return Response({"error": "Base CV not found for the candidate"}, status=status.HTTP_404_NOT_FOUND)

        if "name" in request.data:
            base_cv.name = request.data["name"]
            base_cv.save(update_fields=["name"])

        if "cv_data" in request.data:
            self.handle_cv_data_update(base_cv, request.data["cv_data"], partial=True)

        if "template" in request.data:
            self.handle_template_update(base_cv, request.data["template"], partial=True)

        return Response(CVSerializer(base_cv).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Delete the current CV data and template, and create new ones for the authenticated user's base CV.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="CV name"),
                "cv_data": openapi.Schema(type=openapi.TYPE_OBJECT, description="CV data fields."),
                "template": openapi.Schema(type=openapi.TYPE_OBJECT, description="Template data fields."),
            },
        ),
        responses={
            201: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Base CV or AbstractTemplate not found."),
        },
    )
    def post(self, request):
        candidate = request.user.candidate
        required_keys = {"name", "cv_data", "template"}

        if not required_keys.issubset(request.data.keys()):
            return Response({"error": f"All fields {required_keys} are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve or create the base CV
        base_cv, created = CV.objects.get_or_create(candidate=candidate, cv_type=CV.BASE)
        base_cv.name = request.data["name"]
        base_cv.save(update_fields=["name"])

        self.handle_cv_data_update(base_cv, request.data["cv_data"], partial=False)
        self.handle_template_update(base_cv, request.data["template"], partial=False)

        return Response(CVSerializer(base_cv).data, status=status.HTTP_201_CREATED)


    @swagger_auto_schema(
        operation_description="Delete the CV data and its associated template for the authenticated user's base CV.",
        responses={
            204: openapi.Response(description="No Content"),
            404: openapi.Response(description="Base CV or associated data not found"),
        }
    )
    def delete(self, request):
        candidate = request.user.candidate
        try:
            # Retrieve the base CV for the candidate
            base_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)

            # Delete associated Template if it exists
            if base_cv.template:
                base_cv.template.delete()

            # Finally, delete the base CV itself
            base_cv.delete()

            return Response(status=status.HTTP_204_NO_CONTENT)
        except CV.DoesNotExist:
            return Response({"error": "Base CV not found for the candidate"}, status=status.HTTP_404_NOT_FOUND)


class UpdateOrCreateCVDataView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update or create CV data for a specific CV.",
        request_body=CVDataSerializer,
        responses={
            200: CVDataSerializer(),
            201: CVDataSerializer(),
            400: openapi.Response(description='Bad Request'),
            404: openapi.Response(description='CV not found.')
        }
    )
    def post(self, request):
        # Retrieve or create the CV based on `cv_id`
        id = request.data.get("id")
        candidate = request.user.candidate

        if id:
            # Attempt to retrieve the existing CV, if present
            try:
                cv = CV.objects.get(id=id, candidate=candidate)
                # Update existing CVData
                cv_data, created = CVData.objects.get_or_create(cv=cv)
            except CV.DoesNotExist:
                # Return an error response if the CV does not exist
                return Response(
                    {"error": "CV not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Create a new CV instance and associated CVData for the authenticated user
            cv = CV.objects.create(candidate=candidate)
            cv_data = CVData.objects.create(cv=cv)

        # Serialize and update the CVData fields
        serializer = CVDataSerializer(cv_data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK if id else status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# views.py (or wherever you keep your custom base view)
from rest_framework.views import APIView
from rest_framework.request import Request
from django.http import HttpRequest

# Import your custom AsyncRequest
# Adjust the import path as needed to match your project structure
from .requests import AsyncRequest


class AsyncAPIView(APIView):
    """
    A base async class that:
      - Provides its own as_view() returning an async function
      - Overrides `initialize_request()` to force using AsyncRequest
      - Implements an async `dispatch()` pipeline, so the final request
        has `_async_authenticate()` available.
    """

    @classmethod
    def as_view(cls, **initkwargs):
        """
        Build an async view function from scratch, without calling super().as_view().
        This prevents DRF's default sync pipeline from overshadowing our custom code.
        """
        async def view(request, *args, **kwargs):
            # Instantiate our view class
            self = cls(**initkwargs)
            # Call the async dispatch
            return await self.dispatch(request, *args, **kwargs)

        # Help DRF's schema or browsable API introspection:
        view.cls = cls
        view.initkwargs = initkwargs
        return view

    def initialize_request(self, request, *args, **kwargs):
        """
        Force DRF to create an AsyncRequest rather than rest_framework.request.Request.
        This is critical so `request._async_authenticate()` actually exists.
        """
        parser_context = self.get_parser_context(request)
        return AsyncRequest(
            request,
            parsers=self.get_parsers(),
            authenticators=self.get_authenticators(),
            negotiator=self.get_content_negotiator(),
            parser_context=parser_context,
        )

    async def dispatch(self, request, *args, **kwargs):
        # The default DRF dispatch sets self.headers = {}
        # We must do this ourselves.
        self.headers = {}

        # ... your async logic ...
        request = self.initialize_request(request, *args, **kwargs)
        await self.async_initial(request, *args, **kwargs)

        if request.method.lower() in self.http_method_names:
            handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
        else:
            handler = self.http_method_not_allowed

        response = await handler(request, *args, **kwargs)
        return self.finalize_response(request, response, *args, **kwargs)

    async def async_initial(self, request, *args, **kwargs):
        """
        An async replacement for .initial().
        """
        await self.async_perform_authentication(request)
        self.check_permissions(request)
        self.check_throttles(request)

    async def async_perform_authentication(self, request):
        """
        In an async pipeline, we call `_async_authenticate()` on our AsyncRequest.
        """
        await request._async_authenticate()


class UploadCVView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @swagger_auto_schema(
        operation_description="Upload a CV file to extract data and create/update the CV data.",
        manual_parameters=[
            openapi.Parameter(
                'files',
                openapi.IN_FORM,
                description="CV file to upload",
                type=openapi.TYPE_FILE,
                required=True,
            ),
        ],
        responses={
            201: CVSerializer(),
            400: openapi.Response(description='Please upload exactly one file.'),
            403: openapi.Response(description='Insufficient credits.'),
            500: openapi.Response(description='Failed to extract data from the external API.')
        },
        consumes=["multipart/form-data"],
    )
    async def post(self, request):
        candidate = await sync_to_async(lambda: request.user.candidate)()

        # Check credits asynchronously
        sufficient, credit_cost = await sync_to_async(has_sufficient_credits)(candidate, 'upload_cv')
        if not sufficient:
            return Response(
                {'error': f'Insufficient credits. This action requires {credit_cost} credits.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Ensure exactly one file
        if 'files' not in request.FILES or len(request.FILES.getlist('files')) != 1:
            return Response({'error': 'Please upload exactly one file.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['files']

        # Send file to external API asynchronously
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    settings.EXTERNAL_API_URL,
                    files={'files': (file.name, file.read(), file.content_type)},
                    timeout=None
                )
            except Exception as exc:
                print(exc)
                return Response({'error': f'Failed to contact the external API: {exc}'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if response.status_code == 200:
            extracted_data = response.json()
            # Delete existing CV and CVData if they exist
            existing_cv = await sync_to_async(CV.objects.filter)(candidate=candidate, cv_type=CV.BASE)
            if await sync_to_async(existing_cv.exists)():
                await sync_to_async(existing_cv.delete)()

            # Save file asynchronously
            folder = 'Cvs/'
            file_path = os.path.join(folder, file.name)
            async with aiofiles.open(default_storage.path(file_path), 'wb') as f:
                await f.write(file.read())

            # Create new CV
            cv = await sync_to_async(CV.objects.create)(
                candidate=candidate,
                original_file=file_path
            )

            # Create new CVData from extracted data
            if extracted_data:
                await sync_to_async(CVData.objects.create)(
                    cv=cv,
                    title=extracted_data[0].get('title'),
                    name=extracted_data[0].get('name'),
                    email=extracted_data[0].get('email'),
                    phone=extracted_data[0].get('phone'),
                    age=extracted_data[0].get('age'),
                    city=extracted_data[0].get('city'),
                    work=extracted_data[0].get('work', []),
                    educations=extracted_data[0].get('educations', []),
                    languages=extracted_data[0].get('languages', []),
                    skills=extracted_data[0].get('skills', []),
                    social=extracted_data[0].get('social', []),
                    certifications=extracted_data[0].get('certifications', []),
                    projects=extracted_data[0].get('projects', []),
                    volunteering=extracted_data[0].get('volunteering', []),
                    references=extracted_data[0].get('references', []),
                    headline=extracted_data[0].get('headline'),
                    summary=extracted_data[0].get('summary')
                )

                # Deduct credits asynchronously
                await sync_to_async(deduct_credits)(candidate, 'upload_cv')

                # Serialize and return response
                serialized_data = await sync_to_async(lambda: CVSerializer(cv, context={'request': request}).data)()
                return Response(serialized_data, status=status.HTTP_201_CREATED)

        return Response({'error': 'Failed to extract data from the external API.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LinkedInCVView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @swagger_auto_schema(
        operation_description="Fetch LinkedIn profile data and create/update the CV data.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['linkedin_profile_url'],
            properties={
                'linkedin_profile_url': openapi.Schema(type=openapi.TYPE_STRING, description='LinkedIn profile URL'),
            },
        ),
        responses={
            201: CVDataSerializer(),
            400: openapi.Response(description='Invalid LinkedIn profile URL.'),
            403: openapi.Response(description='Insufficient credits.'),
            500: openapi.Response(description='Failed to fetch LinkedIn profile data.')
        }
    )
    def post(self, request):
        linkedin_url = request.data.get('linkedin_profile_url')

        # Validate LinkedIn URL
        if not linkedin_url or 'linkedin.com/in/' not in linkedin_url:
            return Response({'error': 'Invalid LinkedIn profile URL.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if candidate has credits
        candidate = request.user.candidate
        sufficient, credit_cost = has_sufficient_credits(candidate, 'upload_linkedin_profile')
        if not sufficient:
            return Response(
                {'error': f'Insufficient credits. This action requires {credit_cost} credits.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Call ProxyCurl API to fetch LinkedIn profile data
        headers = {
            'Authorization': f'Bearer {settings.PROXYCURL_API_KEY}'
        }

        params = {
            'linkedin_profile_url': linkedin_url,
            'extra': 'include',
            'github_profile_id': 'include',
            'personal_contact_number': 'include',
            'personal_email': 'include',
            'skills': 'include',
            'use_cache': 'if-recent',
            'fallback_to_cache': 'on-error',
        }

        response = requests.get('https://nubela.co/proxycurl/api/v2/linkedin', headers=headers, params=params)

        if response.status_code == 200:
            profile_data = response.json()
            # profile_data = {'public_identifier': 'salim-elkellouti', 'profile_pic_url': 'https://media.licdn.com/dms/image/v2/D4E03AQGBSM0moSSvXA/profile-displayphoto-shrink_800_800/profile-displayphoto-shrink_800_800/0/1687307448266?e=1733961600&v=beta&t=LnunByFqil0RxnpyhBwwiPtFvV6tGbgh9ByJKJXBncc', 'background_cover_image_url': 'https://media.licdn.com/dms/image/v2/D4E16AQEyZkfW28eAwQ/profile-displaybackgroundimage-shrink_350_1400/profile-displaybackgroundimage-shrink_350_1400/0/1721421996986?e=1733961600&v=beta&t=PTWCJdCzpniZfxSVINJbWc9KkmYWoqpurR9UoJGn2bc', 'first_name': 'Salim', 'last_name': 'Elkellouti', 'full_name': 'Salim Elkellouti', 'follower_count': 154, 'occupation': 'Software Developer at GEEKFACT', 'headline': 'Développeur de logiciels chez GEEKFACT | Master en Systèmes Informatiques et Mobiles', 'summary': 'I am Salim El Kellouti, a dedicated software developer looking for new opportunities.\n\nI hold a Bachelor\'s degree in Computer Engineering and a Master\'s degree in Computer and Mobile Systems from the "Faculté des Sciences et Techniques de Tanger". My academic background laid a solid foundation in the principles of computer science, mathematics, and software engineering, which I\'ve applied effectively throughout my career.\n\nHaving developed my technical expertise through a series of complex projects and internships during my studies, I have a strong grasp of various programming languages and frameworks, including Python, PHP, Flask, Laravel, and Django. While I have substantial experience as a full-stack developer, my passion lies in backend development where I excel at designing and implementing robust and scalable server-side logic.\nMy career goals are centered around deepening my knowledge and expertise in backend architecture to contribute to more efficient and innovative software solutions. I aim to pursue opportunities that challenge me to utilize my skills in creating impactful and enduring technological advancements.', 'country': 'MA', 'country_full_name': 'Morocco', 'city': 'Tanger-Tetouan-Al Hoceima', 'state': None, 'experiences': [{'starts_at': {'day': 1, 'month': 7, 'year': 2024}, 'ends_at': None, 'company': 'GEEKFACT', 'company_linkedin_profile_url': 'https://www.linkedin.com/company/geekfact', 'company_facebook_profile_url': None, 'title': 'Software Developer', 'description': None, 'location': 'Casablanca, Casablanca-Settat, Maroc', 'logo_url': 'https://s3.us-west-000.backblazeb2.com/proxycurl/company/geekfact/profile?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0004d7f56a0400b0000000001%2F20241009%2Fus-west-000%2Fs3%2Faws4_request&X-Amz-Date=20241009T211240Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=0fe11923fb4bdb0e5ece40ceb981d930efab28e210769c519152fc46c5a3a7c5'}, {'starts_at': {'day': 1, 'month': 3, 'year': 2024}, 'ends_at': {'day': 31, 'month': 7, 'year': 2024}, 'company': 'CAMELDEV', 'company_linkedin_profile_url': None, 'company_facebook_profile_url': None, 'title': 'Full-Stack Web and Mobile Developer: Flutter | Django | MySQL', 'description': '-Developing a real estate application using Django and Flutter for posting and searching properties.\n-Implementing advanced search functionality with thorough filters.\n-Integrating AI to convert multi-language descriptions of searched properties into queries, utilizing Celery and Celery Beat for regular updates.\n-Implementing GPS-based alerts to notify users and property owners of proximity to properties.\n-Administering the Django backend to efficiently manage REST APIs while handling media storage on AWS S3 Buckets.\n-Enriching data using Python scrapers configured as AWS Lambda functions.', 'location': 'Tanger-Tétouan-Al Hoceïma, Maroc', 'logo_url': None}, {'starts_at': {'day': 1, 'month': 6, 'year': 2022}, 'ends_at': {'day': 29, 'month': 2, 'year': 2024}, 'company': 'HENNA MEDIA LTD', 'company_linkedin_profile_url': 'https://www.linkedin.com/company/17742480/', 'company_facebook_profile_url': None, 'title': 'Full-Stack Developer: Laravel | Django | MySQL | PostgreSQL', 'description': '-Enhanced backend functionalities using Laravel and MySQL for improved data management and user interaction handling.\n-Implemented responsive templating with Laravel Blade and developed custom JavaScript for dynamic and interactive content delivery.\n-Developed backend systems with Laravel and MySQL to support dynamic content delivery, employing AJAX and vanilla JavaScript to enhance system responsiveness and performance.\n-Created a management dashboard using Laravel, MySQL, and Laravel Blade for handling complex transactions and real-time inventory management.\n-Integrated comprehensive security features including secure logins and role-based access controls to ensure data protection.\n-Developed secure user authentication and member management systems using Laravel and MySQL.\nImplemented multi-factor authentication and session management to enhance security and user interface interactivity using Laravel Blade.', 'location': 'Tanger-Tétouan-Al Hoceïma, Maroc', 'logo_url': None}, {'starts_at': {'day': 1, 'month': 6, 'year': 2021}, 'ends_at': {'day': 31, 'month': 5, 'year': 2022}, 'company': 'Chakir Group', 'company_linkedin_profile_url': None, 'company_facebook_profile_url': None, 'title': 'Python Developer: Python | Selenium | Flask | FasAPI', 'description': '-Engineered advanced web scrapers using Python, employing libraries such as Selenium for automation of web browsers, BeautifulSoup for parsing HTML and XML documents, and Requests for handling HTTP requests. This approach enabled efficient data extraction from various web sources, tailored to specific project requirements.\n\n-Designed and implemented a RESTful API using Flask to facilitate the reception and storage of data extracted by the scrapers. Structured the API to handle requests efficiently, ensuring robust data management through systematic validation, serialization, and storage in a relational database, enhancing data integrity and accessibility.', 'location': None, 'logo_url': None}, {'starts_at': {'day': 1, 'month': 4, 'year': 2020}, 'ends_at': {'day': 30, 'month': 6, 'year': 2020}, 'company': 'Faculté des Sciences et Techniques de Tanger', 'company_linkedin_profile_url': 'https://www.linkedin.com/company/fsttanger', 'company_facebook_profile_url': None, 'title': ' Full-stack Developer intern : Laravel | React | MySQL', 'description': "As part of our final year project to obtain our bachelor's degree, we completed an internal internship supervised by one of our professors, focusing on the development of a centralized web application for patient medical records.\nThe objective of this project was to provide a reliable web-based healthcare system, improve services offered to doctors and patients, and make patients' medical histories available online and accessible everywhere so that doctors can manage cases with less effort.\nWe utilized several technologies for this project, with the most essential being Laravel for managing registration, authentication, and routing at the Back-End, and React.js for the Front-End of our application.", 'location': None, 'logo_url': 'https://s3.us-west-000.backblazeb2.com/proxycurl/company/fsttanger/profile?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0004d7f56a0400b0000000001%2F20241009%2Fus-west-000%2Fs3%2Faws4_request&X-Amz-Date=20241009T211240Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=bdf22c60f7d26a16bf390642817285941e716e8d576aef94ac04c50537ba133c'}], 'education': [{'starts_at': {'day': 1, 'month': 9, 'year': 2021}, 'ends_at': {'day': 31, 'month': 7, 'year': 2024}, 'field_of_study': 'Systèmes Informatiques et Mobiles', 'degree_name': 'Master', 'school': 'Faculty of Science and Technology Tangier', 'school_linkedin_profile_url': 'https://www.linkedin.com/company/fsttanger', 'school_facebook_profile_url': None, 'description': "Pour mon PFE de master en Systèmes Informatiques et Mobiles, j'ai développé une application immobilière utilisant Django et Flutter. L'application propose des annonces immobilières mises à jour par web scraping à partir de sites immobiliers marocains, tout en hébergeant images et vidéos sur AWS S3 et en exécutant les scripts de scraping via AWS Lambda. Elle exploite l'IA pour améliorer la fonctionnalité de recherche, élargissant dynamiquement les recherches avec un dictionnaire de synonymes spécifique au secteur immobilier et convertissant les descriptions textuelles directement en requêtes SQL pour des résultats plus précis. De plus, l'application intègre Google Maps pour les notifications basées sur la proximité et utilise Gmail SMTP pour communiquer directement avec les utilisateurs, démontrant une intégration fluide de diverses technologies pour améliorer l'expérience utilisateur.", 'logo_url': 'https://s3.us-west-000.backblazeb2.com/proxycurl/company/fsttanger/profile?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0004d7f56a0400b0000000001%2F20241009%2Fus-west-000%2Fs3%2Faws4_request&X-Amz-Date=20241009T211240Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=bdf22c60f7d26a16bf390642817285941e716e8d576aef94ac04c50537ba133c', 'grade': None, 'activities_and_societies': None}, {'starts_at': {'day': 1, 'month': 1, 'year': 2019}, 'ends_at': {'day': 31, 'month': 12, 'year': 2020}, 'field_of_study': 'Génie informatique', 'degree_name': 'Licence', 'school': 'Faculty of Science and Technology Tangier', 'school_linkedin_profile_url': 'https://www.linkedin.com/company/fsttanger', 'school_facebook_profile_url': None, 'description': "Dans le cadre de notre projet de fin d'étude, nous avons effectué un stage interne, encadré par l'un de nos professeurs, travaillant sur le sujet du développement d'une application web centralisés des dossiers médicaux des patients.\nLe but de ce travail était la fournissage d'un système Web de santé fiable, l'amélioration des services fournis aux médecins et patients, en rendant l'historique médicale de ce dernier disponible en ligne, et partout pour que les médecins puissent suivre les cas avec moins d'effort. \nNous avons utilisé plusieurs technologies pour realiser ce projet, mais les plus essentiels sont, Laravel, afin de gérer l'enregistrement, l'authentification et le routage au niveau Back-End, et Reactjs pour le Front-End de notre application.", 'logo_url': 'https://s3.us-west-000.backblazeb2.com/proxycurl/company/fsttanger/profile?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0004d7f56a0400b0000000001%2F20241009%2Fus-west-000%2Fs3%2Faws4_request&X-Amz-Date=20241009T211240Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=bdf22c60f7d26a16bf390642817285941e716e8d576aef94ac04c50537ba133c', 'grade': None, 'activities_and_societies': None}, {'starts_at': {'day': 1, 'month': 1, 'year': 2016}, 'ends_at': {'day': 31, 'month': 12, 'year': 2019}, 'field_of_study': 'MATHÉMATIQUES-INFORMATIQUE-PHYSIQUE-CHIMIE', 'degree_name': "Diplôme d'études universitaires scientifiques et techniques (DEUST)", 'school': 'Faculty of Science and Technology Tangier', 'school_linkedin_profile_url': 'https://www.linkedin.com/company/fsttanger', 'school_facebook_profile_url': None, 'description': None, 'logo_url': 'https://s3.us-west-000.backblazeb2.com/proxycurl/company/fsttanger/profile?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0004d7f56a0400b0000000001%2F20241009%2Fus-west-000%2Fs3%2Faws4_request&X-Amz-Date=20241009T211240Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=bdf22c60f7d26a16bf390642817285941e716e8d576aef94ac04c50537ba133c', 'grade': None, 'activities_and_societies': None}], 'languages': [], 'languages_and_proficiencies': [], 'accomplishment_organisations': [], 'accomplishment_publications': [], 'accomplishment_honors_awards': [], 'accomplishment_patents': [], 'accomplishment_courses': [], 'accomplishment_projects': [], 'accomplishment_test_scores': [], 'volunteer_work': [], 'certifications': [], 'connections': 154, 'people_also_viewed': [], 'recommendations': [], 'activities': [], 'similarly_named_profiles': [], 'articles': [], 'groups': [], 'skills': ['Amazon RDS', 'Beautiful Soup', 'Docker', 'Flutter', 'Celery', 'Selenium', 'AWS', 'Flask', 'Fast Api', 'Datalife', 'MariaDB', 'PostgreSQL', 'Amazon Web Services', 'AWS Lambda', 'Django', 'Framework Django REST', 'React.js', 'Laravel', 'MySQL', 'jQuery', 'SQL', 'Git', 'MongoDB', 'NoSQL', 'Vue.js', 'Python (langage de programmation)', 'C', 'WordPress', 'JavaScript', 'Java', 'Firebase', 'API Postman', 'Langage de modélisation unifié (UML)'], 'inferred_salary': {'min': None, 'max': None}, 'gender': None, 'birth_date': None, 'industry': 'Computer Software', 'extra': {'github_profile_id': None, 'twitter_profile_id': None, 'facebook_profile_id': None}, 'interests': [], 'personal_emails': [], 'personal_numbers': []}

            # If the candidate has an existing CV, delete it and its associated CVData
            if CV.objects.filter(candidate=candidate, cv_type=CV.BASE).exists():
                existing_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
                # existing_cv.cv_data.all().delete()
                existing_cv.delete()

            # Extract personal emails and numbers, handling empty lists
            personal_email = profile_data.get('personal_emails', [])
            personal_email = personal_email[0] if personal_email else None

            personal_number = profile_data.get('personal_numbers', [])
            personal_number = personal_number[0] if personal_number else None

            # Map work experience to the required structure
            work_experiences = []
            for experience in profile_data.get('experiences', []):
                work_experiences.append({
                    'job_title': experience.get('title'),
                    'company_name': experience.get('company'),
                    'responsibilities': experience.get('description'),
                    'city': experience.get('location'),
                    'start_date': f"{experience['starts_at']['year']}-{experience['starts_at']['month']:02d}-{experience['starts_at']['day']:02d}" if experience.get('starts_at') else None,
                    'end_date': f"{experience['ends_at']['year']}-{experience['ends_at']['month']:02d}-{experience['ends_at']['day']:02d}" if experience.get('ends_at') else None,
                })

            # Map education to the required structure
            educations = []
            for education in profile_data.get('education', []):
                educations.append({
                    'degree': education.get('degree_name'),
                    'institution': education.get('school'),
                    'start_year': education.get('starts_at', {}).get('year'),
                    'end_year': education.get('ends_at', {}).get('year'),
                })

            # Map languages to the required structure
            languages = []
            for language in profile_data.get('languages_and_proficiencies', []):
                languages.append({
                    'language': language.get('language'),
                    'level': language.get('proficiency'),
                })

            # Map skills to the required structure
            skills = []
            for skill in profile_data.get('skills', []):
                skills.append({
                    'skill': skill,
                    'level': None  # Assuming skill level is not provided by the API
                })

            # Map certifications to the required structure
            certifications = []
            for cert in profile_data.get('certifications', []):
                certifications.append({
                    'certification': cert.get('name'),
                    'institution': cert.get('organization'),
                    'link': cert.get('url'),
                    'date': cert.get('date'),
                })

            # Map social skills
            social_skills = [{'skill': s} for s in profile_data.get('social', [])]

            # Create a new CV (no file to store in this case)
            cv = CV.objects.create(candidate=candidate, original_file=None)

            # Create CVData based on the mapped data
            cv_data = CVData.objects.create(
                cv=cv,
                title=profile_data.get('occupation'),
                name=profile_data.get('full_name'),
                email=personal_email,
                phone=personal_number,
                city=profile_data.get('city'),
                work=work_experiences,
                educations=educations,
                languages=languages,
                skills=skills,
                social=social_skills,
                certifications=certifications,
                headline=profile_data.get('headline'),
                summary=profile_data.get('summary'),
            )

            # Deduct one credit from the candidate
            deduct_credits(candidate, 'upload_linkedin_profile')

            # Serialize and return the CVData response
            serialized_data = CVSerializer(cv, context={'request': request}).data
            # serialized_data.pop('id', None)
            # serialized_data.pop('cv', None)

            return Response(serialized_data, status=status.HTTP_201_CREATED)
        else:
            return Response({'error': 'Failed to fetch LinkedIn profile data. Try Again Later'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class JobLinkCVView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Tailor a CV based on a job link.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['job_link'],
            properties={
                'job_link': openapi.Schema(type=openapi.TYPE_STRING, description='URL of the job posting'),
            },
        ),
        responses={
            200: CVDataSerializer(),
            400: openapi.Response(description='Invalid job link or unsupported domain.'),
            403: openapi.Response(description='Insufficient credits.'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def post(self, request):
        job_link = request.data.get('job_link')

        # Validate the job link
        if not job_link:
            return Response({'error': 'Job link is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not is_valid_job_url(job_link):
            return Response({'error': 'Invalid job link or unsupported domain.'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch the job description
        job_description = fetch_job_description(job_link)
        if not job_description:
            return Response({'error': 'Failed to fetch job description after multiple retries.'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check candidate credits
        candidate = request.user.candidate
        sufficient, credit_cost = has_sufficient_credits(candidate, 'tailor_job_from_link')
        if not sufficient:
            return Response(
                {'error': f'Insufficient credits. This action requires {credit_cost} credits.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Extract job ID
        job_id = extract_job_id(job_link)
        if not job_id:
            return Response({'error': 'Invalid job link, unable to extract job ID.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Ensure the base CV exists and fetch its CVData
        base_cv = CV.objects.filter(candidate=candidate, cv_type=CV.BASE).first()
        if not base_cv or not hasattr(base_cv, 'cv_data'):
            return Response({'error': 'Base CV or associated data is missing.'}, status=status.HTTP_400_BAD_REQUEST)

        base_cv_data = base_cv.cv_data

        # Use the base CV data to construct the candidate profile
        candidate_profile = construct_candidate_profile(base_cv_data)

        # Construct the prompt for Gemini
        prompt = construct_single_job_prompt(candidate_profile, job_description, job_link)
        # Get the response from Gemini for scoring the job
        try:
            gemini_response = get_gemini_response(prompt)
            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
            job_score_data = json.loads(gemini_response)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Create or update the job based on the Gemini response
        job_data = {
            "title": job_score_data.get("title"),
            "description": job_score_data.get("description", job_description),
            "requirements": job_score_data.get("requirements"),
            "company_name": job_score_data.get("company_name"),
            "location": job_score_data.get("location"),
            "employment_type": job_score_data.get("employment_type"),
            "salary_range": job_score_data.get("salary_range"),
            "min_salary": job_score_data.get("min_salary"),
            "max_salary": job_score_data.get("max_salary"),
            "benefits": job_score_data.get("benefits"),
            "skills_required": job_score_data.get("skills_required"),
            "posted_date": job_score_data.get("posted_date"),
            "job_id": job_id,
            "original_url": job_link
        }
        job, job_created = Job.objects.update_or_create(job_id=job_id, defaults=job_data)
        score = job_score_data.get('score', 0)

        # Create the JobSearch with the similarity score
        JobSearch.objects.get_or_create(
            candidate=candidate,
            job=job,
            defaults={"similarity_score": score}
        )

        if score < 50:
            return Response({
                'error': 'The job does not align well with your profile. Proceeding to tailor a resume is not recommended.',
                'job_score_data': job_score_data
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check if a tailored CV for this job already exists
        tailored_cv, created = CV.objects.get_or_create(
            candidate=candidate,
            cv_type=CV.TAILORED,
            job=job
        )

        # Ensure CVData for the tailored CV
        tailored_cv_data, _ = CVData.objects.get_or_create(cv=tailored_cv)

        # Construct the tailored resume prompt
        tailored_prompt = construct_tailored_job_prompt(base_cv_data, candidate, job_description)

        # Get the response from Gemini for tailored CV data
        try:
            tailored_response = get_gemini_response(tailored_prompt)
            tailored_response = (tailored_response.split("```json")[-1]).split("```")[0]
            tailored_data = json.loads(tailored_response)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Update the tailored CVData
        serializer = CVDataSerializer(tailored_cv_data, data=tailored_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            deduct_credits(candidate, 'tailor_job_from_link')
            return Response(CVSerializer(tailored_cv, context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExistingJobCVView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Tailor a CV based on an existing job ID.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['job_id'],
            properties={
                'job_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the existing job'),
            },
        ),
        responses={
            200: CVDataSerializer(),
            400: openapi.Response(description='Bad Request'),
            403: openapi.Response(description='Insufficient credits.'),
            404: openapi.Response(description='Job not found.'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def post(self, request):
        # Validate the provided job ID
        job_id = request.data.get('job_id')
        if not job_id:
            return Response({'error': 'Job ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({'error': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

        candidate = request.user.candidate
        sufficient, credit_cost = has_sufficient_credits(candidate, 'tailor_job_from_existing')
        if not sufficient:
            return Response(
                {'error': f'Insufficient credits. This action requires {credit_cost} credits.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Ensure the base CV exists and fetch its CVData
        base_cv = CV.objects.filter(candidate=candidate, cv_type=CV.BASE).first()
        if not base_cv or not hasattr(base_cv, 'cv_data'):
            return Response({'error': 'Base CV or associated data is missing.'}, status=status.HTTP_400_BAD_REQUEST)

        base_cv_data = base_cv.cv_data

        # Check if JobSearch exists for this candidate and job
        job_search = JobSearch.objects.filter(candidate=candidate, job=job).first()
        if job_search:
            score = job_search.similarity_score
        else:
            # Construct a prompt for Gemini to get only the similarity score
            prompt = construct_only_score_job_prompt(base_cv_data, job.description)
            try:
                gemini_response = get_gemini_response(prompt)
                gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
                score_data = json.loads(gemini_response)
                score = score_data.get("score", 0)
            except Exception as e:
                return Response({'error': f"Failed to fetch score from Gemini: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Save the JobSearch with the calculated score
            JobSearch.objects.create(candidate=candidate, job=job, similarity_score=score)

        # If the score is less than 50, return a "not recommended" response
        if score < 50:
            return Response({
                'message': f'The job does not align well with your profile. The similarity score percentage between this job and your profile according to our estimate is {score}% According to our estimation. Proceeding to tailor a resume is not recommended.',
                'score': score
            }, status=status.HTTP_200_OK)

        # Check if a tailored CV for this job already exists
        tailored_cv, created = CV.objects.get_or_create(
            candidate=candidate,
            cv_type=CV.TAILORED,
            job=job
        )

        # Ensure CVData for the tailored CV
        tailored_cv_data, _ = CVData.objects.get_or_create(cv=tailored_cv)

        # Construct the tailored CV prompt
        tailored_prompt = construct_tailored_job_prompt(base_cv_data, candidate, job.description)

        # Get tailored CV data from Gemini
        try:
            tailored_response = get_gemini_response(tailored_prompt)
            tailored_response = (tailored_response.split("```json")[-1]).split("```")[0]
            tailored_data = json.loads(tailored_response)
        except Exception as e:
            return Response({'error': f"Failed to fetch tailored CV data from Gemini: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Update the tailored CVData
        serializer = CVDataSerializer(tailored_cv_data, data=tailored_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            deduct_credits(candidate, 'tailor_job_from_existing')
            return Response(CVSerializer(tailored_cv, context={'request': request}).data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class JobDescriptionCVView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Tailor a CV based on a provided job description.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['job_description'],
            properties={
                'job_description': openapi.Schema(type=openapi.TYPE_STRING, description='Job description text'),
            },
        ),
        responses={
            200: CVDataSerializer(),
            201: CVDataSerializer(),
            400: openapi.Response(description='Bad Request'),
            403: openapi.Response(description='Insufficient credits.'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def post(self, request):
        job_description = request.data.get('job_description')

        # Ensure the job description is provided
        if not job_description:
            return Response({'error': 'Job description is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the candidate has enough credits
        candidate = request.user.candidate
        sufficient, credit_cost = has_sufficient_credits(candidate, 'tailor_job_from_description')
        if not sufficient:
            return Response(
                {'error': f'Insufficient credits. This action requires {credit_cost} credits.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if the candidate already has CVData
        cv_data_instance = CVData.objects.filter(cv__candidate=candidate).first()

        prompt = construct_tailored_job_prompt(cv_data_instance, candidate, job_description)

        # Get the response from Gemini
        try:
            gemini_response = get_gemini_response(prompt)
            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
            gemini_data = json.loads(gemini_response)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if cv_data_instance:
            # Update existing CVData with the new data
            serializer = CVDataSerializer(cv_data_instance, data=gemini_data, partial=True)
        else:
            # Create a new CV and CVData
            cv = CV.objects.create(candidate=candidate, original_file=None)
            gemini_data['cv'] = cv.id
            serializer = CVDataSerializer(data=gemini_data)

        if serializer.is_valid():
            serializer.save()
            deduct_credits(candidate, 'tailor_job_from_description')
            serialized_data = serializer.data
            serialized_data.pop('id', None)
            serialized_data.pop('cv', None)
            return Response(serialized_data,
                            status=status.HTTP_201_CREATED if not cv_data_instance else status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TriggerScrapingView(APIView):
    permission_classes = [IsAuthenticated]  # Only authenticated users can access this endpoint
    swagger_schema = None

    def post(self, request):
        candidate = request.user.candidate  # Get the authenticated candidate
        keyword = request.data.get('keyword')  # Get keyword from request body
        location = request.data.get('location')  # Get location from request body
        num_jobs_to_scrape = request.data.get('jobCount', candidate.num_jobs_to_scrape)  # Get num_jobs_to_scrape or fallback to candidate setting
        # Check if the required fields are provided
        if not keyword or not location:
            return Response({"error": "Keyword and location are required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger the scraping task manually
        run_scraping_task.delay(candidate_id=candidate.id, keyword=keyword, location=location, num_jobs_to_scrape=int(num_jobs_to_scrape), manual=True)

        return Response({"message": "Job scraping has been triggered manually."}, status=status.HTTP_200_OK)


class TemplateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve the template associated with a Tailored CV.",
        responses={
            200: TemplateSerializer(),
            404: openapi.Response(description='CV not found for candidate or Template not found')
        }
    )
    def get(self, request, id):
        candidate = request.user.candidate

        try:
            cv = CV.objects.get(candidate=candidate, id=id)
        except CV.DoesNotExist:
            return Response({"detail": "CV not found for candidate"}, status=status.HTTP_404_NOT_FOUND)

        if cv.template:
            serializer = TemplateSerializer(cv.template)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Template not found"}, status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(
        operation_description="Create or update the template associated with a Tailored CV.",
        request_body=TemplateSerializer,
        responses={
            200: TemplateSerializer(),
            201: TemplateSerializer(),
            400: openapi.Response(description='Template data is required to create a new template.'),
            404: openapi.Response(description='CV not found for candidate')
        }
    )
    def post(self, request, id):
        candidate = request.user.candidate
        data = request.data
        templateData = data.templateData

        try:
            cv = CV.objects.get(candidate=candidate, id=id)
        except CV.DoesNotExist:
            return Response({"detail": "CV not found for candidate"}, status=status.HTTP_404_NOT_FOUND)

        template_name = templateData.get("template")
        if not template_name:
            return Response({"error": "Template name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            abstract_template = AbstractTemplate.objects.get(name=template_name)
        except AbstractTemplate.DoesNotExist:
            return Response({"error": f"AbstractTemplate with name '{template_name}' not found."}, status=status.HTTP_404_NOT_FOUND)

        template, created = Template.objects.update_or_create(
            id=cv.template.id if cv.template else None,
            defaults={
                'abstract_template': abstract_template,
                'language': templateData.get('language', 'en'),
                'company_logo': templateData.get('company_logo', {}),
                'page': templateData.get('page', {}),
                'certifications': templateData.get('certifications', {}),
                'education': templateData.get('education', {}),
                'experience': templateData.get('experience', {}),
                'volunteering': templateData.get('volunteering', {}),
                'interests': templateData.get('interests', {}),
                'languages': templateData.get('languages', {}),
                'projects': templateData.get('projects', {}),
                'references': templateData.get('references', {}),
                'skills': templateData.get('skills', {}),
                'social': templateData.get('social', {}),
                'theme': templateData.get('theme', {}),
                'personnel': templateData.get('personnel', {}),
                'typography': templateData.get('typography', {}),
            }
        )

        cv.template = template
        cv.save()

        serializer = TemplateSerializer(template)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TopUpView(APIView):
    @swagger_auto_schema(
        operation_description="Create a PayPal order to purchase credits.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['credits', 'pack_id'],
            properties={
                'credits': openapi.Schema(type=openapi.TYPE_INTEGER, description='Number of credits to purchase'),
                'pack_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the credit pack'),
            },
        ),
        responses={
            201: openapi.Response(
                description='Order created',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'orderId': openapi.Schema(type=openapi.TYPE_STRING, description='PayPal order ID'),
                    }
                )
            ),
            400: openapi.Response(description='Invalid credit amount or pack'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def post(self, request):
        credits = request.data.get('credits')
        pack_id = request.data.get('pack_id')

        # Validate the pack
        try:
            pack = Pack.objects.get(id=pack_id, is_active=True)
        except Pack.DoesNotExist:
            return Response({"error": "Invalid or inactive pack"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate credits and fetch the price
        try:
            price_entry = pack.prices.get(credits=credits)
        except Price.DoesNotExist:
            return Response({"error": "Invalid credit amount for the selected pack"}, status=status.HTTP_400_BAD_REQUEST)

        amount = price_entry.price

        # Create the PayPal order request
        create_request = OrdersCreateRequest()
        create_request.prefer("return=representation")
        create_request.request_body({
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "USD",
                    "value": str(amount)
                }
            }]
        })

        # Execute the request
        try:
            response = paypal_client.execute(create_request)
            order_id = response.result.id

            # Save the order to the database
            candidate = request.user.candidate
            CreditOrder.objects.create(
                credits=credits,
                order_id=order_id,
                candidate=candidate
            )

            return Response({"orderId": order_id}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TopUpConfirmView(APIView):

    @swagger_auto_schema(
        operation_description="Confirm a PayPal order and add credits to the candidate's account.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['orderId'],
            properties={
                'orderId': openapi.Schema(type=openapi.TYPE_STRING, description='PayPal order ID'),
            },
        ),
        responses={
            200: openapi.Response(
                description='Order completed',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, description='Status of the order'),
                    }
                )
            ),
            400: openapi.Response(description='Order ID is required or bad request'),
            404: openapi.Response(description='Order not found or already paid'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def post(self, request):
        order_id = request.data.get('orderId')
        candidate = request.user.candidate

        if not order_id:
            return Response({"error": "Order ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch the order to ensure it exists and is associated with the candidate
        try:
            order = CreditOrder.objects.get(order_id=order_id, candidate=candidate, paid=False)
        except CreditOrder.DoesNotExist:
            return Response({"error": "Order not found or already paid"}, status=status.HTTP_404_NOT_FOUND)

        # Capture the order through PayPal
        capture_request = OrdersCaptureRequest(order_id)
        try:
            capture_response = paypal_client.execute(capture_request)
            capture_status = capture_response.result.status

            if capture_status == "COMPLETED":
                with transaction.atomic():
                    # Mark the order as paid
                    order.paid = True
                    order.save()

                    # Increment the candidate's credits
                    candidate.credits += order.credits
                    candidate.save()

                return Response({"status": "COMPLETED"}, status=status.HTTP_200_OK)

            return Response({"status": capture_status}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateTailoredCVView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Create a new tailored CV for a specific job.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['job_id'],
            properties={
                'job_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the job'),
            },
        ),
        responses={
            201: CVDataSerializer(),
            400: openapi.Response(description='Bad Request'),
            404: openapi.Response(description='Job not found.')
        }
    )
    def post(self, request):
        candidate = request.user.candidate
        job_id = request.data.get("job_id")

        if not job_id:
            return Response({"error": "Job ID is required to create a tailored CV."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if a tailored CV for the job already exists
        if CV.objects.filter(candidate=candidate, cv_type=CV.TAILORED, job_id=job_id).exists():
            return Response({"error": "A tailored CV for this job already exists."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the job exists
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        # Create a new tailored CV and associated CVData
        tailored_cv = CV.objects.create(candidate=candidate, cv_type=CV.TAILORED, job=job)
        cv_data = CVData.objects.create(cv=tailored_cv)

        # Serialize and return the data
        serializer = CVDataSerializer(cv_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TailoredCVView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve an individual tailored CV and its associated data.",
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Tailored CV not found."),
        }
    )
    def get(self, request, id):
        candidate = request.user.candidate

        try:
            # Retrieve the tailored CV
            tailored_cv = CV.objects.get(id=id, candidate=candidate, cv_type=CV.TAILORED)
            serializer = CVSerializer(tailored_cv, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CV.DoesNotExist:
            return Response({"error": "Tailored CV not found."}, status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(
        operation_description="Update a tailored CV's data and template.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Tailored CV or associated data not found."),
        },
    )
    def put(self, request, id):
        candidate = request.user.candidate

        # Retrieve the tailored CV
        try:
            tailored_cv = CV.objects.get(id=id, candidate=candidate, cv_type=CV.TAILORED)
        except CV.DoesNotExist:
            return Response({"error": "Tailored CV not found or does not belong to the authenticated user."},
                            status=status.HTTP_404_NOT_FOUND)

        # Update CVData
        if "cv_data" in request.data:
            try:
                cv_data = CVData.objects.get(cv=tailored_cv)
            except CVData.DoesNotExist:
                cv_data = CVData(cv=tailored_cv)

            cv_data_serializer = CVDataSerializer(cv_data, data=request.data.get("cv_data"), partial=False)
            if not cv_data_serializer.is_valid():
                return Response(cv_data_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            cv_data_serializer.save()

        # Update Template
        if "template" in request.data:
            template_data = request.data.get("template")
            template_name = template_data.get("templateData", {}).get("template")
            if not template_name:
                return Response({"error": "Template name is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                abstract_template = AbstractTemplate.objects.get(name=template_name)
            except AbstractTemplate.DoesNotExist:
                return Response({"error": f"AbstractTemplate with name '{template_name}' not found."},
                                status=status.HTTP_404_NOT_FOUND)

            # Remove unwanted keys from templateData
            template_data["templateData"].pop("identity", None)
            template_data["templateData"].pop("template", None)

            template, created = Template.objects.update_or_create(
                id=tailored_cv.template.id if tailored_cv.template else None,
                defaults={
                    'abstract_template': abstract_template,
                    'language': template_data.get('language', 'en'),
                    **template_data.get("templateData", {})
                }
            )

            tailored_cv.template = template
            tailored_cv.save()

        return Response(CVSerializer(tailored_cv, context={"request": request}).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Partially update a tailored CV's data and template.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="Tailored CV or associated data not found."),
        },
    )
    def patch(self, request, id):
        candidate = request.user.candidate

        # Retrieve the tailored CV
        try:
            tailored_cv = CV.objects.get(id=id, candidate=candidate, cv_type=CV.TAILORED)
        except CV.DoesNotExist:
            return Response({"error": "Tailored CV not found or does not belong to the authenticated user."},
                            status=status.HTTP_404_NOT_FOUND)

        # Partially update CVData
        if "cv_data" in request.data:
            try:
                cv_data = CVData.objects.get(cv=tailored_cv)
            except CVData.DoesNotExist:
                cv_data = CVData(cv=tailored_cv)

            cv_data_serializer = CVDataSerializer(cv_data, data=request.data.get("cv_data"), partial=True)
            if not cv_data_serializer.is_valid():
                return Response(cv_data_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            cv_data_serializer.save()

        # Partially update Template
        if "template" in request.data:
            template_data = request.data.get("template")
            template_name = template_data.get("templateData", {}).get("template")
            if not template_name:
                return Response({"error": "Template name is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                abstract_template = AbstractTemplate.objects.get(name=template_name)
            except AbstractTemplate.DoesNotExist:
                return Response({"error": f"AbstractTemplate with name '{template_name}' not found."},
                                status=status.HTTP_404_NOT_FOUND)

            # Remove unwanted keys from templateData
            template_data["templateData"].pop("identity", None)
            template_data["templateData"].pop("template", None)

            template, created = Template.objects.update_or_create(
                id=tailored_cv.template.id if tailored_cv.template else None,
                defaults={
                    'abstract_template': abstract_template,
                    'language': template_data.get('language', 'en'),
                    **template_data.get("templateData", {})
                }
            )

            tailored_cv.template = template
            tailored_cv.save()

        return Response(CVSerializer(tailored_cv, context={"request": request}).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Delete a tailored CV with its associated template.",
        responses={
            204: openapi.Response(description='Tailored CV deleted successfully.'),
            404: openapi.Response(description='Tailored CV not found or does not belong to the authenticated user.')
        }
    )
    def delete(self, request, id):
        candidate = request.user.candidate

        try:
            tailored_cv = CV.objects.get(id=id, candidate=candidate, cv_type=CV.TAILORED)

            # Delete associated Template if it exists
            if tailored_cv.template:
                tailored_cv.template.delete()

            # Delete the tailored CV
            tailored_cv.delete()

            return Response({"detail": "Tailored CV deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except CV.DoesNotExist:
            return Response({"error": "Tailored CV not found or does not belong to the authenticated user."}, status=status.HTTP_404_NOT_FOUND)


class CVFilter(django_filters.FilterSet):
    # Filters for CV fields
    job_title = django_filters.CharFilter(field_name="job__title", lookup_expr="icontains")
    job_location = django_filters.CharFilter(field_name="job__location", lookup_expr="icontains")
    created_at_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    # Filters for CVData fields
    name = django_filters.CharFilter(field_name="cv_data__name", lookup_expr="icontains")
    email = django_filters.CharFilter(field_name="cv_data__email", lookup_expr="icontains")
    city = django_filters.CharFilter(field_name="cv_data__city", lookup_expr="icontains")
    skills = django_filters.CharFilter(method="filter_by_skills")

    class Meta:
        model = CV
        fields = [
            "job_title", "job_location", "created_at_after", "created_at_before",
            "name", "email", "city", "skills"
        ]

    def filter_by_skills(self, queryset, name, value):
        skills = [skill.strip().lower() for skill in value.split(",")]
        for skill in skills:
            queryset = queryset.filter(Q(cv_data__skills__icontains=skill))
        return queryset


class CandidateTailoredCVsPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class CandidateCVsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CandidateTailoredCVsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CVFilter
    serializer_class = CVSerializer

    def get_queryset(self):
        # Retrieve all CVs for the authenticated candidate
        candidate = self.request.user.candidate
        return CV.objects.filter(candidate=candidate).select_related("cv_data", "job")

    @swagger_auto_schema(
        operation_description="Retrieve a list of CVs for the authenticated user, with the base CV always appearing first.",
        manual_parameters=[
            openapi.Parameter('job_title', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job title'),
            openapi.Parameter('job_location', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by job location'),
            openapi.Parameter('created_at_after', openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME, description='Filter CVs created after this date'),
            openapi.Parameter('created_at_before', openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME, description='Filter CVs created before this date'),
            openapi.Parameter('name', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by name'),
            openapi.Parameter('email', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by email'),
            openapi.Parameter('city', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by city'),
            openapi.Parameter('skills', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Filter by skills (comma-separated)'),
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page number'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Number of items per page'),
        ],
        responses={200: CVSerializer(many=True)},
        security=[{'Bearer': []}],
    )
    def list(self, request, *args, **kwargs):
        candidate = self.request.user.candidate

        # Retrieve the base CV
        try:
            base_cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
        except CV.DoesNotExist:
            base_cv = None

        # Apply filters to the remaining CVs (excluding the base CV)
        queryset = self.filter_queryset(self.get_queryset().exclude(id=base_cv.id if base_cv else None))

        # Combine base CV with the filtered queryset
        if base_cv:
            queryset = [base_cv] + list(queryset)

        # Paginate the combined queryset
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CVSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = CVSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


class RemoveFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Remove a job from the candidate's favorites.",
        responses={
            204: openapi.Response(description='Favorite removed successfully.'),
            404: openapi.Response(description='Favorite not found.')
        }
    )
    def delete(self, request, job_id):
        candidate = request.user.candidate

        favorite = Favorite.objects.filter(candidate=candidate, job_id=job_id).first()
        if not favorite:
            return Response({"error": "Favorite not found."}, status=status.HTTP_404_NOT_FOUND)

        favorite.delete()
        return Response({"detail": "Favorite removed successfully."}, status=status.HTTP_204_NO_CONTENT)


class GetFavoriteScoresView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get similarity scores for favorite jobs.",
        responses={
            200: openapi.Response(
                description='Job searches created successfully.',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'detail': openapi.Schema(type=openapi.TYPE_STRING, description='Detail message'),
                        'scores': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                            type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Job ID'),
                                    'score': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description='Similarity score'),
                                }
                            ),
                            description='List of scores'
                        ),
                    }
                )
            ),
            400: openapi.Response(description='Bad Request'),
            500: openapi.Response(description='Internal Server Error')
        }
    )
    def get(self, request):
        candidate = request.user.candidate
        base_cv = CV.objects.filter(candidate=candidate, cv_type=CV.BASE).first()
        if not base_cv or not hasattr(base_cv, 'cv_data'):
            return Response({'error': 'Base CV or associated data is missing.'}, status=status.HTTP_400_BAD_REQUEST)
        base_cv_data = base_cv.cv_data
        candidate_profile = construct_candidate_profile(base_cv_data)

        # Exclude jobs that already have JobSearch
        favorite_jobs = Favorite.objects.filter(candidate=candidate)
        job_ids_with_search = JobSearch.objects.filter(candidate=candidate).values_list('job_id', flat=True)
        jobs_to_compare = favorite_jobs.exclude(job_id__in=job_ids_with_search)

        if not jobs_to_compare.exists():
            return Response({"detail": "No new jobs to compare."}, status=status.HTTP_200_OK)

        jobs_data = [
            {
                "id": job.job.id,
                "title": job.job.title,
                "description": job.job.description,
                "requirements": ', '.join(job.job.requirements or []),
                "skills": ', '.join(job.job.skills_required or [])
            }
            for job in jobs_to_compare
        ]

        prompt = construct_similarity_prompt(candidate_profile, jobs_data)
        # Get scores from Gemini
        try:
            gemini_response = get_gemini_response(prompt)
            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
            scores = json.loads(gemini_response)

            for score_data in scores:
                job_id = score_data['id']
                score = score_data['score']

                job = Job.objects.get(id=job_id)
                JobSearch.objects.create(candidate=candidate, job=job, similarity_score=score)

            return Response({"detail": "Job searches created successfully.", "scores": scores}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserTemplateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve the template associated with the authenticated user's base CV.",
        responses={
            200: TemplateSerializer(),
            404: openapi.Response(description='Base CV not found for candidate or Template not found')
        }
    )
    def get(self, request):
        candidate = request.user.candidate

        try:
            cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
        except CV.DoesNotExist:
            return Response({"detail": "Base CV not found for candidate"}, status=status.HTTP_404_NOT_FOUND)

        if cv.template:
            serializer = TemplateSerializer(cv.template)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Template not found"}, status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(
        operation_description="Create or update the template associated with the authenticated user's base CV.",
        request_body=TemplateSerializer,
        responses={
            200: TemplateSerializer(),
            201: TemplateSerializer(),
            400: openapi.Response(description='Template data is required to create a new template.'),
            404: openapi.Response(description='Base CV not found for candidate')
        }
    )
    def post(self, request):
        candidate = request.user.candidate
        data = request.data
        templateData = data.get("templateData")
        try:
            cv = CV.objects.get(candidate=candidate, cv_type=CV.BASE)
        except CV.DoesNotExist:
            return Response({"detail": "Base CV not found for candidate"}, status=status.HTTP_404_NOT_FOUND)

        template_name = templateData.get("template")
        if not template_name:
            return Response({"error": "Template name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            abstract_template = AbstractTemplate.objects.get(name=template_name)
        except AbstractTemplate.DoesNotExist:
            return Response({"error": f"AbstractTemplate with name '{template_name}' not found."}, status=status.HTTP_404_NOT_FOUND)

        template, created = Template.objects.update_or_create(
            id=cv.template.id if cv.template else None,
            defaults={
                'abstract_template': abstract_template,
                'language': templateData.get('language', 'en'),
                'company_logo': templateData.get('company_logo', {}),
                'page': templateData.get('page', {}),
                'certifications': templateData.get('certifications', {}),
                'education': templateData.get('education', {}),
                'experience': templateData.get('experience', {}),
                'volunteering': templateData.get('volunteering', {}),
                'interests': templateData.get('interests', {}),
                'languages': templateData.get('languages', {}),
                'projects': templateData.get('projects', {}),
                'references': templateData.get('references', {}),
                'skills': templateData.get('skills', {}),
                'social': templateData.get('social', {}),
                'theme': templateData.get('theme', {}),
                'personnel': templateData.get('personnel', {}),
                'typography': templateData.get('typography', {}),
            }
        )

        cv.template = template
        cv.save()

        serializer = TemplateSerializer(template)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PackPricesView(APIView):
    """
    View to retrieve all active packs with their associated prices.
    """
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_description="Retrieve all active packs with their associated prices.",
        responses={
            200: openapi.Response(
                description="List of packs with prices.",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Pack ID'),
                            'name': openapi.Schema(type=openapi.TYPE_STRING, description='Pack name'),
                            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Pack description'),
                            'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Pack active status'),
                            'prices': openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'credits': openapi.Schema(type=openapi.TYPE_INTEGER, description='Number of credits'),
                                        'price': openapi.Schema(type=openapi.TYPE_STRING, description='Price of the credits'),
                                    }
                                )
                            )
                        }
                    )
                )
            ),
            404: openapi.Response(description="No active packs found.")
        }
    )
    def get(self, request):
        # Retrieve all active packs with their associated prices
        packs = Pack.objects.filter(is_active=True).prefetch_related('prices')
        if not packs.exists():
            return Response({"error": "No active packs found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PackSerializer(packs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AbstractTemplateListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve all available abstract templates.",
        responses={
            200: AbstractTemplateSerializer(many=True),
        }
    )
    def get(self, request):
        abstract_templates = AbstractTemplate.objects.all()
        serializer = AbstractTemplateSerializer(abstract_templates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CVDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "GET":
            return []  # No authentication required for GET requests
        return [permission() for permission in self.permission_classes]

    @swagger_auto_schema(
        operation_description="Retrieve a CV along with its data and template.",
        responses={
            200: "CV data and template retrieved successfully.",
            404: openapi.Response(description="CV not found."),
        }
    )
    def get(self, request, id):
        try:
            # Retrieve the CV by ID
            cv = CV.objects.get(id=id)

            # Serialize the CV, including template and other data
            serializer = CVSerializer(cv, context={'request': request})

            return Response(serializer.data, status=status.HTTP_200_OK)

        except CV.DoesNotExist:
            return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)

    @swagger_auto_schema(
        operation_description="Update a CV's data and template by ID.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="CV name"),
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="CV or AbstractTemplate not found."),
        },
    )
    def put(self, request, id):
        try:
            # Retrieve the CV
            cv = CV.objects.get(id=id, candidate=request.user.candidate)
        except CV.DoesNotExist:
            return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)

        # Validate required keys
        required_keys = {"name", "cv_data", "template"}
        if not required_keys.issubset(request.data.keys()):
            return Response({"error": f"All fields {required_keys} are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Update name
        cv.name = request.data.get("name", cv.name)
        cv.save(update_fields=["name"])

        # Update CVData
        self.update_cv_data(cv, request.data["cv_data"], partial=False)

        # Update Template
        self.update_template(cv, request.data["template"], partial=False)

        return Response(CVSerializer(cv, context={"request": request}).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Partially update a CV's data and template by ID.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="CV name"),
                "cv_data": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="The CV data fields.",
                    properties={
                        "title": openapi.Schema(type=openapi.TYPE_STRING, description="CV title"),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's name"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's email"),
                        "phone": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's phone number"),
                        "age": openapi.Schema(type=openapi.TYPE_INTEGER, description="Candidate's age"),
                        "city": openapi.Schema(type=openapi.TYPE_STRING, description="Candidate's city"),
                        "work": openapi.Schema(type=openapi.TYPE_OBJECT, description="Work experience details"),
                        "educations": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education details"),
                        "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages known"),
                        "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills"),
                        "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests"),
                        "social": openapi.Schema(type=openapi.TYPE_OBJECT, description="Social profiles"),
                        "certifications": openapi.Schema(type=openapi.TYPE_OBJECT, description="Certifications"),
                        "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects"),
                        "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                       description="Volunteering experiences"),
                        "references": openapi.Schema(type=openapi.TYPE_OBJECT, description="References"),
                        "headline": openapi.Schema(type=openapi.TYPE_STRING, description="Professional headline"),
                        "summary": openapi.Schema(type=openapi.TYPE_STRING, description="Summary or bio"),
                    },
                ),
                "template": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description="Template data fields.",
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                        "reference": openapi.Schema(type=openapi.TYPE_STRING, description="Template reference."),
                        "language": openapi.Schema(type=openapi.TYPE_STRING, description="Template language."),
                        "templateData": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="The nested template data structure.",
                            properties={
                                "identity": openapi.Schema(type=openapi.TYPE_STRING, description="Template identity."),
                                "template": openapi.Schema(type=openapi.TYPE_STRING, description="Template name."),
                                "company_logo": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Company logo details."),
                                "page": openapi.Schema(type=openapi.TYPE_OBJECT, description="Page layout details."),
                                "certifications": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                                 description="Certifications layout."),
                                "education": openapi.Schema(type=openapi.TYPE_OBJECT, description="Education layout."),
                                "experience": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Experience layout."),
                                "volunteering": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                               description="Volunteering layout."),
                                "interests": openapi.Schema(type=openapi.TYPE_OBJECT, description="Interests layout."),
                                "languages": openapi.Schema(type=openapi.TYPE_OBJECT, description="Languages layout."),
                                "projects": openapi.Schema(type=openapi.TYPE_OBJECT, description="Projects layout."),
                                "references": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="References layout."),
                                "skills": openapi.Schema(type=openapi.TYPE_OBJECT, description="Skills layout."),
                                "social": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                         description="Social profiles layout."),
                                "theme": openapi.Schema(type=openapi.TYPE_OBJECT, description="Theme settings."),
                                "personnel": openapi.Schema(type=openapi.TYPE_OBJECT, description="Personnel layout."),
                                "typography": openapi.Schema(type=openapi.TYPE_OBJECT,
                                                             description="Typography settings."),
                            },
                        ),
                    },
                ),
            },
        ),
        responses={
            200: CVSerializer(),
            400: openapi.Response(description="Bad Request"),
            404: openapi.Response(description="CV or AbstractTemplate not found."),
        },
    )
    def patch(self, request, id):
        try:
            # Retrieve the CV
            cv = CV.objects.get(id=id, candidate=request.user.candidate)
        except CV.DoesNotExist:
            return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)

        # Allowed keys
        allowed_keys = {"name", "cv_data", "template"}
        request_keys = set(request.data.keys())

        # Validate at least one key is valid
        if not request_keys.intersection(allowed_keys):
            return Response({"error": f"At least one of {allowed_keys} is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Update name if present
        if "name" in request.data:
            cv.name = request.data["name"]
            cv.save(update_fields=["name"])

        # Update CVData if present
        if "cv_data" in request.data:
            self.update_cv_data(cv, request.data["cv_data"], partial=True)

        # Update Template if present
        if "template" in request.data:
            self.update_template(cv, request.data["template"], partial=True)

        return Response(CVSerializer(cv, context={"request": request}).data, status=status.HTTP_200_OK)

    def update_cv_data(self, cv, cv_data, partial):
        """
        Helper to update or create CVData.
        """
        try:
            cv_data_instance = CVData.objects.get(cv=cv)
        except CVData.DoesNotExist:
            cv_data_instance = CVData(cv=cv)

        serializer = CVDataSerializer(cv_data_instance, data=cv_data, partial=partial)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)
        serializer.save()

    def update_template(self, cv, template_data, partial):
        """
        Helper to update or create Template.
        """
        template_name = template_data.get("templateData", {}).get("template")
        if not template_name:
            raise serializers.ValidationError({"error": "Template name is required."})

        try:
            abstract_template = AbstractTemplate.objects.get(name=template_name)
        except AbstractTemplate.DoesNotExist:
            raise serializers.ValidationError({"error": f"AbstractTemplate '{template_name}' not found."})

        # Remove unwanted keys
        template_data["templateData"].pop("identity", None)
        template_data["templateData"].pop("template", None)

        template, created = Template.objects.update_or_create(
            id=cv.template.id if cv.template else None,
            defaults={
                'abstract_template': abstract_template,
                'language': template_data.get('language', 'en'),
                **template_data.get("templateData", {})
            }
        )

        cv.template = template
        cv.save()

    @swagger_auto_schema(
        operation_description="Delete a CV by ID, including its associated template if present.",
        responses={
            204: openapi.Response(description="CV deleted successfully."),
            404: openapi.Response(description="CV not found."),
        },
    )
    def delete(self, request, id):
        try:
            # Retrieve the CV by ID
            cv = CV.objects.get(id=id, candidate=request.user.candidate)

            # Delete associated Template if it exists
            if cv.template:
                cv.template.delete()

            # Delete the CV
            cv.delete()

            return Response({"detail": "CV deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

        except CV.DoesNotExist:
            return Response({"error": "CV not found."}, status=status.HTTP_404_NOT_FOUND)


class DownloadCVPDFView(APIView):
    """
    API endpoint to download the generated CV PDF.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Download the generated PDF of a CV for the authenticated user.",
        manual_parameters=[
            openapi.Parameter(
                'id', openapi.IN_PATH, description="ID of the CV", type=openapi.TYPE_INTEGER, required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="File response with the PDF for download",
                schema=openapi.Schema(
                    type=openapi.TYPE_FILE,
                    description="PDF file of the CV"
                ),
            ),
            400: openapi.Response(
                description="Bad Request - PDF not generated for this CV.",
                examples={"application/json": {"error": "PDF not generated for this CV."}}
            ),
            404: openapi.Response(
                description="Not Found - CV or PDF file does not exist.",
                examples={"application/json": {"error": "CV not found"}}
            ),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request, id):
        try:
            cv = CV.objects.get(id=id, candidate=request.user.candidate)

            # Return the PDF file for download
            if not cv.generated_pdf:
                return Response({"error": "PDF not generated for this CV."}, status=400)

            file_path = cv.generated_pdf.path
            if not os.path.exists(file_path):
                raise Http404("File not found")

            return FileResponse(open(file_path, "rb"), as_attachment=True, filename=f"{cv.name}.pdf")

        except CV.DoesNotExist:
            return Response({"error": "CV not found"}, status=404)