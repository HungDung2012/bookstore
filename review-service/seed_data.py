import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'review_service.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from app.models import Review

Review.objects.all().delete()

reviews = [
    # Book 1 - LOTR
    {"book_id": 1, "user_id": 3, "rating": 5, "title": "An absolute masterpiece!", "comment": "Tolkien created an entire world. The depth of lore is unmatched in any other book I've read."},
    {"book_id": 1, "user_id": 4, "rating": 5, "title": "Magical journey", "comment": "If you haven't read it, stop everything and read it now."},
    # Book 2 - 1984
    {"book_id": 2, "user_id": 3, "rating": 5, "title": "Chillingly relevant", "comment": "Written in 1949 yet feels like it could be written today. A must-read."},
    {"book_id": 2, "user_id": 4, "rating": 4, "title": "Powerful dystopia", "comment": "Dark, disturbing, brilliant. Orwell was a visionary."},
    # Book 6 - Dune
    {"book_id": 6, "user_id": 3, "rating": 5, "title": "Greatest sci-fi ever", "comment": "The world-building in Dune is unparalleled. Frank Herbert created a universe."},
    {"book_id": 6, "user_id": 4, "rating": 4, "title": "Dense but rewarding", "comment": "Takes patience to get into but absolutely worth it."},
    # Book 10 - Harry Potter
    {"book_id": 10, "user_id": 3, "rating": 5, "title": "Timeless classic", "comment": "I've read this 5 times. Still magical every time."},
    {"book_id": 10, "user_id": 4, "rating": 5, "title": "Perfect for all ages", "comment": "Whether you're 10 or 40, this book is pure magic."},
    # Book 15 - Sapiens
    {"book_id": 15, "user_id": 3, "rating": 5, "title": "Mind-blowing perspective", "comment": "Changed how I see humanity and our history. Everyone should read this."},
    {"book_id": 15, "user_id": 4, "rating": 4, "title": "Fascinating read", "comment": "Harari's insights are deep and thought-provoking."},
    # Book 17 - Atomic Habits
    {"book_id": 17, "user_id": 3, "rating": 5, "title": "Life-changing!", "comment": "Applied the 1% rule and it genuinely transformed my productivity."},
    {"book_id": 17, "user_id": 4, "rating": 5, "title": "Practical and effective", "comment": "Unlike other self-help books, this one gives you actual systems that work."},
]

for r in reviews:
    Review.objects.create(**r)

print(f"Created {Review.objects.count()} reviews")
