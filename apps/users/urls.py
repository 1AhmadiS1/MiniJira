from django.urls import path
from apps.users.views import (
    LoginView,
    MeView,
    PasswordChangeView,
    RefreshView,
    RegisterView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", PasswordChangeView.as_view(), name="change_password"),
]
