from django.urls import path, include
from .views import (
    SignUpView, LoginView, UploadCVView, LinkedInCVView, JobDescriptionCVView, LogoutView, ChangePasswordView,
    CandidateJobsView, CVDataView, TemplateDetailView, TopUpView, TopUpConfirmView, CandidateAppliedJobsView,
    JobLinkCVView, TailoredCVView, ExistingJobCVView, UserTemplateView, GetJobScoresByIdsView,
    CandidateCVsView, RemoveFavoriteView, GetFavoriteScoresView, CandidateFavoriteJobsView, JobClickView,
    UserProfileView, PackPricesView, AbstractTemplateListView, CVDetailView, DownloadCVPDFView, JobDetailView,
    RecentSearchTermsView, PasswordResetRequestView, PasswordResetConfirmView, VerifyEmailView, custom_google_callback,
    JobLocationsView, AdsByTypeView, GenerateJobCVScoreView
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('auth/signup/', SignUpView.as_view(), name='signup'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    # path('auth/password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    # path('auth/password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset-confirm/<int:user_id>/<str:token>/', PasswordResetConfirmView.as_view(),
         name='password-reset-confirm'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('auth/social/google/callback/', custom_google_callback, name='google_callback'),

    path('users/me/', UserProfileView.as_view(), name='user-profile'),
    path('users/me/password/', ChangePasswordView.as_view(), name='change-password'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path('cvs/base/upload/', UploadCVView.as_view(), name='upload_cv'),
    path('cvs/base/linkedin/', LinkedInCVView.as_view(), name='linkedin_cv'),
    path('cvs/base/', CVDataView.as_view(), name='cv-data'),
    path('cvs/base/template/', UserTemplateView.as_view(), name='user-template'),
    # path('cvs/tailored/', CandidateTailoredCVsView.as_view(), name='candidate-tailored-cvs'),
    path('cvs/', CandidateCVsView.as_view(), name='candidate-tailored-cvs'),
    path('cvs/tailored/<int:id>/', TailoredCVView.as_view(), name='update_tailored_cv'),
    path('cvs/tailored/job-description/', JobDescriptionCVView.as_view(), name='job_description_cv'),
    path('cvs/tailored/job-link/', JobLinkCVView.as_view(), name='job_link_cv'),
    path('cvs/tailored/existing-job/', ExistingJobCVView.as_view(), name='existing_job_cv'),
    path('cvs/tailored/<int:id>/template/', TemplateDetailView.as_view(), name='template-detail'),
    path('cvs/<int:id>/', CVDetailView.as_view(), name='cv_detail'),
    path('cvs/<int:id>/download/', DownloadCVPDFView.as_view(), name='download_cv_pdf'),

    path('jobs/', CandidateJobsView.as_view(), name='candidate-jobs'),
    path('jobs/<int:id>/', JobDetailView.as_view(), name='job-detail'),
    path('jobs/favorites/', CandidateFavoriteJobsView.as_view(), name='candidate-favorite-jobs'),
    path('jobs/favorites/<int:job_id>/', RemoveFavoriteView.as_view(), name='remove_favorite'),
    path('jobs/favorites/scores/', GetFavoriteScoresView.as_view(), name='favorite_scores'),
    path('jobs/applied/', CandidateAppliedJobsView.as_view(), name='candidate-applied-jobs'),
    path('jobs/scores/', GetJobScoresByIdsView.as_view(), name='job_scores_by_ids'),
    path('jobs/score/cv/', GenerateJobCVScoreView.as_view(), name='job_score_by_cv_id'),
    path('jobs/clicks/<int:job_id>/', JobClickView.as_view(), name='job-click'),

    path('templates/', AbstractTemplateListView.as_view(), name='abstract-template-list'),

    path('credits/create-order/', TopUpView.as_view(), name='top-up'),
    path('credits/confirm-order/', TopUpConfirmView.as_view(), name='top-up-confirm'),
    path('credits/prices/', PackPricesView.as_view(), name='top-up-confirm'),

    path('searches/recent/', RecentSearchTermsView.as_view(), name='recent-search-terms'),

    path('accounts/', include('allauth.urls')),
    path('accounts/', include('allauth.socialaccount.urls')),

    path('locations/', JobLocationsView.as_view(), name='job-locations'),

    path('ads/', AdsByTypeView.as_view(), name='ads-by-type'),

]