import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "book_service.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from app.models import Book, Category, Publisher, Staff


categories = [
    "Classic Literature",
    "Science Fiction",
    "Fantasy",
    "Non-Fiction",
    "Mystery & Thriller",
    "Self-Development",
]

publishers = [
    {
        "name": "Penguin Books",
        "defaults": {"address": "80 Strand, London", "email": "info@penguin.co.uk"},
    },
    {
        "name": "HarperCollins",
        "defaults": {"address": "New York, NY", "email": "info@harpercollins.com"},
    },
    {
        "name": "Vintage Books",
        "defaults": {"address": "New York, NY", "email": "info@vintage.com"},
    },
    {
        "name": "Del Rey",
        "defaults": {"address": "New York, NY", "email": "info@delrey.com"},
    },
]

staff_members = [
    {
        "email": "alice@bookstore.com",
        "defaults": {"name": "Alice Johnson", "role": "manager"},
    },
    {
        "email": "bob@bookstore.com",
        "defaults": {"name": "Bob Smith", "role": "staff"},
    },
]

for category_name in categories:
    Category.objects.update_or_create(name=category_name)

publisher_lookup = {}
for publisher_data in publishers:
    publisher, _ = Publisher.objects.update_or_create(
        name=publisher_data["name"],
        defaults=publisher_data["defaults"],
    )
    publisher_lookup[publisher.name] = publisher

for staff_data in staff_members:
    Staff.objects.update_or_create(
        email=staff_data["email"],
        defaults=staff_data["defaults"],
    )

category_lookup = {category.name: category for category in Category.objects.all()}

books = [
    {
        "title": "The Lord of the Rings",
        "author": "J.R.R. Tolkien",
        "price": "24.99",
        "stock": 50,
        "category": "Fantasy",
        "publisher": "HarperCollins",
    },
    {
        "title": "1984",
        "author": "George Orwell",
        "price": "12.99",
        "stock": 80,
        "category": "Classic Literature",
        "publisher": "Penguin Books",
    },
    {
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "price": "11.99",
        "stock": 65,
        "category": "Classic Literature",
        "publisher": "Vintage Books",
    },
    {
        "title": "To Kill a Mockingbird",
        "author": "Harper Lee",
        "price": "13.99",
        "stock": 70,
        "category": "Classic Literature",
        "publisher": "HarperCollins",
    },
    {
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "price": "9.99",
        "stock": 90,
        "category": "Classic Literature",
        "publisher": "Penguin Books",
    },
    {
        "title": "Dune",
        "author": "Frank Herbert",
        "price": "18.99",
        "stock": 45,
        "category": "Science Fiction",
        "publisher": "Del Rey",
    },
    {
        "title": "The Hitchhiker's Guide to the Galaxy",
        "author": "Douglas Adams",
        "price": "14.99",
        "stock": 60,
        "category": "Science Fiction",
        "publisher": "Penguin Books",
    },
    {
        "title": "Ender's Game",
        "author": "Orson Scott Card",
        "price": "15.99",
        "stock": 40,
        "category": "Science Fiction",
        "publisher": "HarperCollins",
    },
    {
        "title": "Brave New World",
        "author": "Aldous Huxley",
        "price": "12.99",
        "stock": 55,
        "category": "Science Fiction",
        "publisher": "Vintage Books",
    },
    {
        "title": "Harry Potter and the Philosopher's Stone",
        "author": "J.K. Rowling",
        "price": "19.99",
        "stock": 100,
        "category": "Fantasy",
        "publisher": "HarperCollins",
    },
    {
        "title": "The Name of the Wind",
        "author": "Patrick Rothfuss",
        "price": "16.99",
        "stock": 35,
        "category": "Fantasy",
        "publisher": "Del Rey",
    },
    {
        "title": "A Game of Thrones",
        "author": "George R.R. Martin",
        "price": "22.99",
        "stock": 42,
        "category": "Fantasy",
        "publisher": "HarperCollins",
    },
    {
        "title": "And Then There Were None",
        "author": "Agatha Christie",
        "price": "10.99",
        "stock": 75,
        "category": "Mystery & Thriller",
        "publisher": "Penguin Books",
    },
    {
        "title": "Gone Girl",
        "author": "Gillian Flynn",
        "price": "14.99",
        "stock": 50,
        "category": "Mystery & Thriller",
        "publisher": "Vintage Books",
    },
    {
        "title": "Sapiens: A Brief History of Humankind",
        "author": "Yuval Noah Harari",
        "price": "17.99",
        "stock": 60,
        "category": "Non-Fiction",
        "publisher": "Vintage Books",
    },
    {
        "title": "A Brief History of Time",
        "author": "Stephen Hawking",
        "price": "15.99",
        "stock": 45,
        "category": "Non-Fiction",
        "publisher": "Penguin Books",
    },
    {
        "title": "Atomic Habits",
        "author": "James Clear",
        "price": "16.99",
        "stock": 80,
        "category": "Self-Development",
        "publisher": "HarperCollins",
    },
    {
        "title": "The 7 Habits of Highly Effective People",
        "author": "Stephen R. Covey",
        "price": "14.99",
        "stock": 55,
        "category": "Self-Development",
        "publisher": "HarperCollins",
    },
]

for book_data in books:
    Book.objects.update_or_create(
        title=book_data["title"],
        author=book_data["author"],
        defaults={
            "price": book_data["price"],
            "stock": book_data["stock"],
            "category": category_lookup[book_data["category"]],
            "publisher": publisher_lookup[book_data["publisher"]],
        },
    )

print(f"Seeded {Category.objects.count()} categories")
print(f"Seeded {Publisher.objects.count()} publishers")
print(f"Seeded {Book.objects.count()} books")
print(f"Seeded {Staff.objects.count()} staff")

