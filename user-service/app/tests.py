from rest_framework.test import APIClient

from django.test import TestCase

from .models import User


class UserAuthRoleTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_defaults_role_to_customer(self):
        response = self.client.post(
            "/auth/register/",
            {
                "username": "newcustomer",
                "email": "newcustomer@example.com",
                "password": "secret123",
                "full_name": "New Customer",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newcustomer")
        self.assertEqual(user.role, "customer")
        self.assertEqual(response.json()["user"]["role"], "customer")

    def test_login_returns_explicit_role_for_staff_user(self):
        staff_user = User.objects.create(
            username="staffer",
            email="staffer@example.com",
            role="staff",
            full_name="Staff Member",
        )
        staff_user.set_password("secret123")
        staff_user.save()

        response = self.client.post(
            "/auth/login/",
            {
                "username": "staffer",
                "password": "secret123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "staff")
