from app.models import Book, Staff, Category, Publisher

# Create categories
cat_fiction = Category.objects.create(name='Fiction')
cat_scifi = Category.objects.create(name='Science Fiction')

# Create publishers
pub_peng = Publisher.objects.create(name='Penguin Books', email='contact@penguin.com')
pub_tor = Publisher.objects.create(name='Tor Books', address='175 Fifth Ave, NY')

# Create Staff Member
staff = Staff.objects.create(name='Alice Manager', email='alice@bookstore.com', role='admin')

# Create Books (With relationships)
b1 = Book.objects.create(title='The Great Gatsby', author='F. Scott Fitzgerald', price=10.99, stock=50, category=cat_fiction, publisher=pub_peng)
b2 = Book.objects.create(title='Dune', author='Frank Herbert', price=20.50, stock=30, category=cat_scifi, publisher=pub_tor)
b3 = Book.objects.create(title='1984', author='George Orwell', price=15.00, stock=100, category=cat_scifi, publisher=pub_peng)

print(f'Created {Book.objects.count()} books, {Staff.objects.count()} staff members.')
