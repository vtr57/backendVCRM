from django.urls import path

from apps.users.views import LoginAPIView, MeAPIView, RefreshAPIView, RegisterAPIView

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="auth-register"),
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshAPIView.as_view(), name="auth-refresh"),
    path("auth/me/", MeAPIView.as_view(), name="auth-me"),
]
