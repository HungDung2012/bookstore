import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "user_service.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from app.models import User


users = [
    {
        "username": "admin",
        "defaults": {
            "email": "admin@bookstore.com",
            "full_name": "Admin User",
            "role": "admin",
        },
        "password": "admin123",
    },
    {
        "username": "staff1",
        "defaults": {
            "email": "staff@bookstore.com",
            "full_name": "Nguyen Van Staff",
            "phone": "0901234567",
            "role": "staff",
        },
        "password": "staff123",
    },
    {
        "username": "customer1",
        "defaults": {
            "email": "customer1@gmail.com",
            "full_name": "Tran Thi Khach",
            "phone": "0912345678",
            "address": "123 Le Loi, Q1, HCM",
            "role": "customer",
        },
        "password": "customer123",
    },
    {
        "username": "customer2",
        "defaults": {
            "email": "customer2@gmail.com",
            "full_name": "Le Van Mua",
            "phone": "0923456789",
            "address": "456 Nguyen Hue, Q1, HCM",
            "role": "customer",
        },
        "password": "customer123",
    },
]

for item in users:
    user, _ = User.objects.update_or_create(
        username=item["username"],
        defaults=item["defaults"],
    )
    user.set_password(item["password"])
    user.save(update_fields=["password_hash"])

print(f"Seeded {User.objects.count()} users")

