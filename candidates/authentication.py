# myapp/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.settings import api_settings
from asgiref.sync import sync_to_async


class HybridJWTAuthentication(JWTAuthentication):
    """
    A single class that works for both sync and async views:
      - .authenticate(...) for sync pipeline
      - async def async_authenticate(...) for async pipeline
    """
    user_id_claim = api_settings.USER_ID_CLAIM
    user_id_field = api_settings.USER_ID_FIELD
    user_model = get_user_model()

    def authenticate(self, request):
        """
        Synchronous method called by normal DRF pipeline (sync views).
        This can do the usual SimpleJWT logic or call self.get_user() directly.
        """
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)  # normal sync call
        return (user, validated_token)

    async def async_authenticate(self, request):
        """
        Async method for custom async pipeline (async views).
        No .authenticate() is called here—our custom pipeline calls async_authenticate().
        """
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)

        # Wrap the ORM fetch in sync_to_async to avoid SynchronousOnlyOperation
        try:
            user = await sync_to_async(self.user_model.objects.get)(
                **{self.user_id_field: validated_token[self.user_id_claim]}
            )
        except self.user_model.DoesNotExist:
            self.raise_invalid_user()

        return (user, validated_token)
