from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def complete_login(self, request, sociallogin):
        """
        Override to bypass redirection and return JWT tokens directly.
        """
        super().complete_login(request, sociallogin)  # Ensure the login is completed

        user = sociallogin.user
        if not user.is_active:
            return JsonResponse({'error': 'Account is inactive.'}, status=403)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        return JsonResponse({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=200)

    def get_login_redirect_url(self, request):
        """
        Override the default redirection behavior to return a dummy URL.
        This is required to avoid breaking allauth logic but won't be used.
        """
        return "/dummy/"
