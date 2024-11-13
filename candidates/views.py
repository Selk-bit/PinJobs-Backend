from rest_framework import viewsets
from .models import Candidate, CV, CVData, Job, JobSearch, Payment, CreditPurchase, Template, Modele, CreditOrder
from .serializers import (CandidateSerializer, CVSerializer, CVDataSerializer, JobSerializer, JobSearchSerializer,
                          PaymentSerializer, CreditPurchaseSerializer, TemplateSerializer)
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
from .utils import get_gemini_response
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
from .utils import paypal_client, PRICE_TABLE
from paypalcheckoutsdk.orders import OrdersCreateRequest, OrdersCaptureRequest
from django.db import transaction


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

    def get(self, request):
        # Get the authenticated candidate
        candidate = request.user.candidate

        # Get the filter params from request
        filters = request.query_params
        # Apply filters for the Job model using the JobFilter
        job_filter = JobFilter(filters, queryset=Job.objects.all())
        jobs = job_filter.qs

        # Apply additional filtering on JobSearch for the current candidate
        job_searches = JobSearch.objects.filter(candidate=candidate)

        # Merge job data with the related job search
        results = []
        for job in jobs:
            try:
                # Find the JobSearch for the specific job and candidate
                job_search = job_searches.get(job=job)

                # Serialize the job and job search data
                job_data = JobSerializer(job).data
                job_data['job_search'] = JobSearchSerializer(job_search).data

                results.append(job_data)
            except JobSearch.DoesNotExist:
                continue  # Skip jobs that don't have a JobSearch for the candidate

        # Sorting logic: sort by similarity score or posted date
        sort_by = request.query_params.get('sort_by', 'similarity_score')
        print(sort_by)
        if sort_by == 'posted_date':
            # Sort by posted_date if it exists, otherwise by similarity_score
            results.sort(
                key=lambda x: (
                    x['posted_date'] is None,  # False if posted_date is not None
                    x['posted_date'] or x['job_search']['similarity_score'],
                ),
                reverse=True
            )
        else:  # Default sorting by similarity score
            results = sorted(results, key=lambda x: x['job_search']['similarity_score'], reverse=True)

        # Apply pagination
        paginator = self.CustomPagination()
        paginated_results = paginator.paginate_queryset(results, request)

        return paginator.get_paginated_response(paginated_results)



class DeleteJobSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, job_id):
        candidate = request.user.candidate

        try:
            # Fetch the JobSearch that belongs to the candidate and includes the job
            job_search = get_object_or_404(JobSearch, candidate=candidate, job__id=job_id)

            # Delete the JobSearch
            job_search.delete()

            return Response({"detail": "JobSearch deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except JobSearch.DoesNotExist:
            return Response({"detail": "JobSearch not found for this candidate."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UpdateJobSearchStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        candidate = request.user.candidate

        try:
            # Fetch the job search that belongs to the candidate and includes the job
            job_search = get_object_or_404(JobSearch, candidate=candidate, job__id=job_id)

            # Update the job search status from 'matched' to 'applied'
            if job_search.status == 'matched':
                job_search.status = 'applied'
                job_search.save()

                return Response({"detail": "Job search status updated to 'applied'."}, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Job search is already 'applied'."}, status=status.HTTP_400_BAD_REQUEST)

        except JobSearch.DoesNotExist:
            return Response({"detail": "Job search not found for this candidate."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        candidate = Candidate.objects.get(user=user)
        candidate_data = CandidateSerializer(candidate).data

        return Response(candidate_data, status=status.HTTP_200_OK)


class UpdateCandidateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        # Extract the current user's candidate instance
        candidate = get_object_or_404(Candidate, user=request.user)

        # Allowed fields for updating
        allowed_fields = [
            'first_name', 'last_name', 'phone', 'age', 'city', 'country',
            'num_jobs_to_scrape', 'scrape_interval', 'scrape_unit'
        ]

        # Only update fields that are present in the request data and allowed
        update_data = {key: value for key, value in request.data.items() if key in allowed_fields}

        serializer = CandidateSerializer(candidate, data=update_data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

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

    def get(self, request):
        # Get the authenticated candidate
        candidate = request.user.candidate

        # Retrieve the CVData for the candidate
        try:
            cv_data = CVData.objects.get(cv__candidate=candidate)
            serializer = CVDataSerializer(cv_data)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CVData.DoesNotExist:
            return Response({"error": "CVData not found for the candidate"}, status=status.HTTP_404_NOT_FOUND)


class DeleteCVView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, cv_id):
        # Get the authenticated candidate
        candidate = request.user.candidate

        try:
            # Retrieve the CV associated with the candidate and the given cv_id
            cv = CV.objects.get(id=cv_id, candidate=candidate)

            # Retrieve the Template and Modele associated with the CV, if they exist
            template = cv.template
            modele = template.templateData if template else None

            # Delete the CVData associated with the CV
            CVData.objects.filter(cv=cv).delete()

            # Delete the CV
            cv.delete()

            # Delete the Template and Modele if they exist
            if template:
                if modele:
                    modele.delete()
                template.delete()

            return Response({"detail": "CV, associated CVData, Template, and Modele deleted successfully"},
                            status=status.HTTP_204_NO_CONTENT)

        except CV.DoesNotExist:
            return Response({"error": "CV not found or does not belong to the authenticated user"},
                            status=status.HTTP_404_NOT_FOUND)


class UpdateOrCreateCVDataView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Retrieve or create the CV based on `cv_id`
        cv_id = request.data.get("cv_id")
        candidate = request.user.candidate

        if cv_id:
            # Attempt to retrieve the existing CV, if present
            try:
                cv = CV.objects.get(id=cv_id, candidate=candidate)
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
            return Response(serializer.data, status=status.HTTP_200_OK if cv_id else status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UploadCVView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Check if the candidate has enough credits
        candidate = request.user.candidate
        if candidate.credits <= 0:
            return Response({'error': 'No credits available. Please purchase more credits.'}, status=status.HTTP_403_FORBIDDEN)

        # Ensure exactly one file is provided
        if 'files' not in request.FILES or len(request.FILES.getlist('files')) != 1:
            return Response({'error': 'Please upload exactly one file.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['files']  # Get the single file

        # Send the file to the external API for extraction
        response = requests.post(
            settings.EXTERNAL_API_URL,
            files={'files': file}
        )

        if response.status_code == 200:
            extracted_data = response.json()  # Get the extracted data from the external API

            # If the user already has a CV, delete the existing CV and CVData
            if CV.objects.filter(candidate=candidate).exists():
                existing_cv = CV.objects.get(candidate=candidate)
                existing_cv.cv_data.all().delete()  # Use the related_name 'cv_data' to delete associated CVData
                existing_cv.delete()  # Delete the existing CV

            # Save the file in the 'Cvs' folder after successful data extraction
            folder = 'Cvs/'
            file_name = default_storage.save(os.path.join(folder, file.name), file)
            file_path = default_storage.path(file_name)

            # Create a new CV for the authenticated candidate
            cv = CV.objects.create(
                candidate=candidate,
                original_file=file_name  # Save the file path
            )

            # Create new CVData from the extracted data
            response_data = []
            if extracted_data:
                cv_data = CVData.objects.create(
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

                # Serialize data and remove "id" and "cv" fields
                serialized_data = CVDataSerializer(cv_data).data
                serialized_data.pop('id', None)
                serialized_data.pop('cv', None)
                # response_data.append(serialized_data)

                candidate.credits -= 1
                candidate.save()

                # Respond with the created CVData excluding "id" and "cv" fields
                return Response(serialized_data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'Failed to extract data from the external API.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'error': 'Failed to extract data from the external API.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LinkedInCVView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        linkedin_url = request.data.get('linkedin_profile_url')

        # Validate LinkedIn URL
        if not linkedin_url or 'linkedin.com/in/' not in linkedin_url:
            return Response({'error': 'Invalid LinkedIn profile URL.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if candidate has credits
        candidate = request.user.candidate
        if candidate.credits <= 0:
            return Response({'error': 'No credits available. Please purchase more credits.'}, status=status.HTTP_403_FORBIDDEN)

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
            if CV.objects.filter(candidate=candidate).exists():
                existing_cv = CV.objects.get(candidate=candidate)
                existing_cv.cv_data.all().delete()
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
            candidate.credits -= 1
            candidate.save()

            # Serialize and return the CVData response
            serialized_data = CVDataSerializer(cv_data).data
            serialized_data.pop('id', None)
            serialized_data.pop('cv', None)

            return Response(serialized_data, status=status.HTTP_201_CREATED)
        else:
            return Response({'error': 'Failed to fetch LinkedIn profile data.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class JobDescriptionCVView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_description = request.data.get('job_description')

        # Ensure the job description is provided
        if not job_description:
            return Response({'error': 'Job description is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the candidate has enough credits
        candidate = request.user.candidate
        if candidate.credits <= 0:
            return Response({'error': 'No credits available. Please purchase more credits.'},
                            status=status.HTTP_403_FORBIDDEN)

        # Check if the candidate already has CVData
        cv_data_instance = CVData.objects.filter(cv__candidate=candidate).first()

        if cv_data_instance:
            # Use the name from the existing CVData if available
            name = cv_data_instance.name if cv_data_instance.name else f"{candidate.first_name} {candidate.last_name}"

            # Determine which fields are missing
            missing_fields = {
                "age": cv_data_instance.age,
                "work": cv_data_instance.work,
                "educations": cv_data_instance.educations,
            }

            # Construct the prompt to ask for missing fields only
            prompt = f"""
                You are tasked with generating a JSON representation of a resume based on a job description.
                The resume should intelligently match the job requirements, but you should not copy the job description verbatim.
                Instead, create a resume that fits the job's requirements by tailoring certain fields appropriately.

                Leave fields like work experiences, education, and other existing fields empty, except for the missing fields indicated below:

                **Skills**: Include a list of relevant hard skills based on the job description, ensuring they align with the requirements without exaggerating. Hard skills emphasized in the job description should have an advanced level, while others can have an intermediate level to retain a realistic skill set.
                **Social**: Include a list of relevant soft skills based on the job description.
                **Certifications**: Add relevant online certifications that could be helpful for the job role, choosing from widely available sources like Coursera, or other similar websites you can think of.
                **Languages**: Include any languages that could be relevant for the job.
                **Summary**: Write a brief summary that showcases the candidate as a good fit for the role without making any false claims.
                **Projects**: Add one or two relevant projects, keeping them realistic and plausible for a candidate with similar qualifications.
                **Interests**: Randomly generate a few interests.
                **Age**: Leave age value as I passed it without any change.
                **Work**: Leave work array as I passed it without any change.
                **Educations**: Leave educations array as I passed it without any change.

                If a city or country is found in the job description, use it as the candidate's location.

                Return the data as a JSON with the following structure:
                {{
                    "title": "<job_title>",
                    "name": "{name}",
                    "email": "{candidate.user.email}",
                    "phone": "{candidate.phone}",
                    "age": {missing_fields['age']},
                    "city": "<city>",
                    "work": {missing_fields['work']},
                    "educations": {missing_fields['educations']},
                    "languages": [
                        {{
                            "language": "<language_name>",
                            "level": "<proficiency>"
                        }}
                    ],
                    "skills": [
                        {{
                            "skill": "<hard_skill_name>",
                            "level": "<hard_skill_level>"
                        }}
                    ],
                    "social": [
                        {{
                            "skill": "<soft_skill_name>"
                        }}
                    ],
                    "certifications": [
                        {{
                            "certification": "<certification_title>",
                            "institution": "<website_name>",
                            "link": "<certification_link>",
                            "date": null
                        }}
                    ],
                    "projects": [
                        {{
                            "project_name": "<project_name>",
                            "description": "<project_description>",
                            "start_date": "",
                            "end_date": ""
                        }}
                    ],
                    "interests": [
                        {{
                            "interest": "<interest_1>"
                        }}
                    ],
                    "headline": null,
                    "summary": "<tailored_summary>"
                }}

                Here is the job description:
                {job_description}
            """
        else:
            # Construct the full prompt if no CVData exists
            prompt = f"""
                You are tasked with generating a JSON representation of a resume based on a job description.
                The resume should intelligently match the job requirements, but you should not copy the job description verbatim.
                Instead, create a resume that fits the job's requirements by tailoring certain fields appropriately.

                You must leave the work experiences and education fields empty, as these should be filled only by the candidate.
                However, you should intelligently fill the following fields to fit the job description:

                **Skills**: Include a list of relevant hard skills based on the job description, ensuring they align with the requirements without exaggerating. Hard skills emphasized in the job description should have an advanced level, while others can have an intermediate level to retain a realistic skill set.
                **Social**: Include a list of relevant soft skills based on the job description.
                **Certifications**: Add relevant online certifications that could be helpful for the job role, choosing from widely available sources like Coursera, or other similar websites you can think of.
                **Languages**: Include any languages that could be relevant for the job.
                **Summary**: Write a brief summary that showcases the candidate as a good fit for the role without making any false claims.
                **Projects**: Add one or two relevant projects, keeping them realistic and plausible for a candidate with similar qualifications.
                **Interests**: Randomly generate a few interests.

                If a city or country is found in the job description, use it as the candidate's location.

                Return the data as a JSON with the following structure:
                {{
                    "title": "<job_title>",
                    "name": "{candidate.first_name} {candidate.last_name}",
                    "email": "{candidate.user.email}",
                    "phone": "{candidate.phone}",
                    "age": null,
                    "city": "<city>",
                    "work": [],
                    "educations": [],
                    "languages": [
                        {{
                            "language": "<language_name>",
                            "level": "<proficiency>"
                        }}
                    ],
                    "skills": [
                        {{
                            "skill": "<hard_skill_name>",
                            "level": "<hard_skill_level>"
                        }}
                    ],
                    "social": [
                        {{
                            "skill": "<soft_skill_name>"
                        }}
                    ],
                    "certifications": [
                        {{
                            "certification": "<certification_title>",
                            "institution": "<website_name>",
                            "link": "<certification_link>",
                            "date": null
                        }}
                    ],
                    "projects": [
                        {{
                            "project_name": "<project_name>",
                            "description": "<project_description>",
                            "start_date": "",
                            "end_date": ""
                        }}
                    ],
                    "interests": [
                        {{
                            "interest": "<interest_1>"
                        }}
                    ],
                    "headline": null,
                    "summary": "<tailored_summary>"
                }}

                Here is the job description:
                {job_description}
            """

        # Get the response from Gemini
        try:
            gemini_response = get_gemini_response(prompt)
            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
            print(gemini_response)
            gemini_data = json.loads(gemini_response)
        except Exception as e:
            print(e)
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
            candidate.credits -= 1
            candidate.save()
            serialized_data = serializer.data
            serialized_data.pop('id', None)
            serialized_data.pop('cv', None)
            return Response(serialized_data,
                            status=status.HTTP_201_CREATED if not cv_data_instance else status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TriggerScrapingView(APIView):
    permission_classes = [IsAuthenticated]  # Only authenticated users can access this endpoint

    def post(self, request):
        candidate = request.user.candidate  # Get the authenticated candidate
        keyword = request.data.get('keyword')  # Get keyword from request body
        location = request.data.get('location')  # Get location from request body
        num_jobs_to_scrape = request.data.get('num_jobs_to_scrape', candidate.num_jobs_to_scrape)  # Get num_jobs_to_scrape or fallback to candidate setting

        # Check if the required fields are provided
        if not keyword or not location:
            return Response({"error": "Keyword and location are required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger the scraping task manually
        run_scraping_task(candidate_id=candidate.id, keyword=keyword, location=location, num_jobs_to_scrape=num_jobs_to_scrape, manual=True)

        return Response({"message": "Job scraping has been triggered manually."}, status=status.HTTP_200_OK)


class TemplateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        candidate = request.user.candidate
        cv = CV.objects.filter(candidate=candidate).first()

        if cv and cv.template:
            serializer = TemplateSerializer(cv.template)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({"detail": "Template not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        candidate = request.user.candidate
        data = request.data
        # Get the CV for the candidate
        cv = CV.objects.filter(candidate=candidate).first()
        if not cv:
            return Response({"detail": "CV not found for candidate"}, status=status.HTTP_404_NOT_FOUND)

        # Check if template exists in CV
        template = cv.template
        created = False

        # Handle creation or updating of Modele associated with Template
        modele_data = data.pop('templateData', None)
        if not template:
            # Create new Modele and Template if they don't exist
            if modele_data:
                modele = Modele.objects.create(**modele_data)
                template = Template.objects.create(
                    name=data.get('name', ''),
                    language=data.get('language', 'en'),
                    reference=data.get('reference', None),
                    templateData=modele
                )
                cv.template = template
                cv.save()
                created = True
        else:
            # Update existing Modele
            if modele_data and template.templateData:
                for attr, value in modele_data.items():
                    setattr(template.templateData, attr, value)
                template.templateData.save()

            # Update Template fields
            for attr, value in data.items():
                setattr(template, attr, value)
            template.save()

        # Serialize and return updated or created Template data
        serializer = TemplateSerializer(template)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TopUpView(APIView):
    def post(self, request):
        credits = request.data.get('credits')

        # Validate credits amount
        if credits not in PRICE_TABLE:
            return Response({"error": "Invalid credit amount"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate the price based on the credits
        amount = PRICE_TABLE[credits]

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