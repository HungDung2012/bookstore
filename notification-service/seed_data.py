import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'notification_service.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from app.models import Notification

Notification.objects.all().delete()

notifs = [
    {"user_id": 3, "type": "system",    "title": "Welcome to Microstore! 📚", "message": "Hi customer1! Explore our collection of 18 curated books. Happy reading!"},
    {"user_id": 4, "type": "system",    "title": "Welcome to Microstore! 📚", "message": "Hi customer2! Explore our collection of 18 curated books. Happy reading!"},
    {"user_id": 3, "type": "promotion", "title": "🔥 Flash Sale — 20% off Sci-Fi!", "message": "This week only: get 20% off all Science Fiction books. Use code SCIFI20 at checkout."},
    {"user_id": 4, "type": "promotion", "title": "📖 New arrivals just dropped!", "message": "Atomic Habits and Sapiens are now in stock. Grab them before they sell out!"},
]
for n in notifs:
    Notification.objects.create(**n)

print(f"Created {Notification.objects.count()} notifications")
