# myapp/requests.py

from rest_framework.request import Request
from django.contrib.auth.models import AnonymousUser


class AsyncRequest(Request):
    """
    An async-friendly Request that can handle an async authentication pipeline.
    """

    async def _async_authenticate(self):
        """
        Async version of DRF's _authenticate logic.
        We'll call each authenticator's 'async_authenticate(self)' if it exists.
        """
        if not hasattr(self, '_user'):
            self._user, self._auth = await self._async_do_authenticate()
        return self._user

    async def _async_do_authenticate(self):
        for authenticator in self.authenticators:
            # Check if the authenticator has an async method:
            if hasattr(authenticator, 'async_authenticate'):
                user_auth_tuple = await authenticator.async_authenticate(self)
            else:
                # fallback: use normal .authenticate if there's no async method
                user_auth_tuple = authenticator.authenticate(self)

            if user_auth_tuple is not None:
                return user_auth_tuple

        # If none returned a user, use AnonymousUser
        return AnonymousUser(), None
