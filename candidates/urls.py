from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CandidateViewSet, CVViewSet, CVDataViewSet, JobViewSet, JobSearchViewSet,
    PaymentViewSet, CreditPurchaseViewSet, SignUpView, LoginView, UploadCVView, LinkedInCVView, JobDescriptionCVView,
    TriggerScrapingView, LogoutView, CurrentUserView, UpdateCandidateView, ChangePasswordView
)
from django.contrib.auth import views as auth_views


router = DefaultRouter()
router.register(r'candidates', CandidateViewSet)
router.register(r'cvs', CVViewSet)
router.register(r'cvdata', CVDataViewSet)
router.register(r'jobs', JobViewSet)
router.register(r'jobsearches', JobSearchViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'creditpurchases', CreditPurchaseViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('current/', CurrentUserView.as_view(), name='current-user'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('upload-cv/', UploadCVView.as_view(), name='upload_cv'),
    path('linkedin-cv/', LinkedInCVView.as_view(), name='linkedin_cv'),
    path('job-description-cv/', JobDescriptionCVView.as_view(), name='job_description_cv'),
    path('scrape-jobs/', TriggerScrapingView.as_view(), name='trigger_scraping'),
    path('candidate/update/', UpdateCandidateView.as_view(), name='update-candidate'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
