from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .consumers import NotificationConsumer

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('candidates.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

websocket_urlpatterns = [
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]