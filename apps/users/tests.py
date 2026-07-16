from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

User = get_user_model()


class HealthCheckTests(APITestCase):
    def test_health_check_reports_database_and_cache(self):
        resp = self.client.get(reverse("health"))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.json(),
            {
                "status": "ok",
                "checks": {"database": True, "cache": True},
            },
        )


class GeneralThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.throttle_rates = patch.dict(
            SimpleRateThrottle.THROTTLE_RATES,
            {"anon": "2/minute", "user": "2/minute"},
        )
        self.throttle_rates.start()

    def tearDown(self):
        self.throttle_rates.stop()
        cache.clear()

    def test_anonymous_requests_are_throttled_by_ip(self):
        url = reverse("register")

        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_authenticated_requests_are_throttled_by_user(self):
        user = User.objects.create_user(
            email="throttle@example.com",
            password="supersecret123",
            first_name="Throttle",
            last_name="Test",
        )
        self.client.force_authenticate(user=user)
        url = reverse("me")

        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


class AuthEndpointTests(APITestCase):
    def test_register_creates_user(self):
        resp = self.client.post(
            reverse("register"),
            {
                "email": "alice@example.com",
                "first_name": "Alice",
                "last_name": "A",
                "password": "supersecret123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", resp.data)
        self.assertTrue(User.objects.filter(email="alice@example.com").exists())

    def test_register_short_password_rejected(self):
        resp = self.client.post(
            reverse("register"),
            {
                "email": "bob@example.com",
                "first_name": "Bob",
                "last_name": "B",
                "password": "short",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_jwt(self):
        User.objects.create_user(
            email="carol@example.com",
            password="supersecret123",
            first_name="Carol",
            last_name="C",
        )
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "carol@example.com", "password": "supersecret123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_token_refresh(self):
        User.objects.create_user(
            email="grace@example.com",
            password="supersecret123",
            first_name="Grace",
            last_name="G",
        )
        login = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "grace@example.com", "password": "supersecret123"},
            format="json",
        )
        resp = self.client.post(
            reverse("token_refresh"),
            {"refresh": login.data["refresh"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)

    def test_me_requires_auth(self):
        resp = self.client.get(reverse("me"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        user = User.objects.create_user(
            email="dave@example.com",
            password="supersecret123",
            first_name="Dave",
            last_name="D",
        )
        self.client.force_authenticate(user=user)
        resp = self.client.get(reverse("me"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "dave@example.com")

    def test_change_password(self):
        user = User.objects.create_user(
            email="erin@example.com",
            password="oldpassword123",
            first_name="Erin",
            last_name="E",
        )
        self.client.force_authenticate(user=user)
        resp = self.client.post(
            reverse("change_password"),
            {"old_password": "oldpassword123", "new_password": "newpassword123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password("newpassword123"))

    def test_change_password_wrong_old(self):
        user = User.objects.create_user(
            email="frank@example.com",
            password="oldpassword123",
            first_name="Frank",
            last_name="F",
        )
        self.client.force_authenticate(user=user)
        resp = self.client.post(
            reverse("change_password"),
            {"old_password": "wrongpassword", "new_password": "newpassword123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
