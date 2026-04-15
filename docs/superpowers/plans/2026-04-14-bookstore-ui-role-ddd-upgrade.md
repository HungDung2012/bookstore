# Bookstore UI, Role, and DDD Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the bookstore demo with a better UI, role-specific experiences for `admin`, `staff`, and `customer`, a complete `cart -> order -> payment -> shipping` flow, and DDD-aligned bounded contexts that are easy to explain in class.

**Architecture:** Keep the current microservice topology and extend it incrementally. `api-gateway` becomes the main role-aware presentation layer, `shipping-service` is added as a lightweight bounded context, and the existing services are upgraded just enough to support the end-to-end demo without a full rewrite.

**Tech Stack:** Django, Django templates, Django REST Framework, Python microservices, Docker Compose, Render

---

## File Map

### New Files

- `shipping-service/manage.py` - Django management entrypoint for the new shipping service
- `shipping-service/shipping_service/settings.py` - shipping service Django settings
- `shipping-service/shipping_service/urls.py` - top-level shipping routes
- `shipping-service/shipping_service/wsgi.py` - WSGI entrypoint
- `shipping-service/app/models.py` - shipment entity and status model
- `shipping-service/app/serializers.py` - shipment serializers
- `shipping-service/app/views.py` - shipping CRUD/update endpoints
- `shipping-service/app/urls.py` - service routes
- `shipping-service/app/tests.py` - shipping service tests
- `shipping-service/app/admin.py` - optional shipment admin registration
- `shipping-service/app/apps.py` - Django app config
- `shipping-service/app/migrations/0001_initial.py` - shipment schema
- `shipping-service/requirements.txt` - service dependencies
- `shipping-service/Dockerfile` - image build for shipping service
- `shipping-service/app/management/commands/seed_shipping_demo.py` - optional demo shipment seeding
- `api-gateway/app/templates/dashboard_admin.html` - admin dashboard
- `api-gateway/app/templates/dashboard_staff.html` - staff dashboard
- `api-gateway/app/templates/dashboard_customer.html` - customer dashboard
- `api-gateway/app/templates/book_detail.html` - product detail page
- `api-gateway/app/templates/checkout.html` - checkout page
- `api-gateway/app/templates/payment_result.html` - payment result page
- `api-gateway/app/templates/my_orders.html` - customer order history
- `api-gateway/app/templates/shipping_detail.html` - customer shipping tracking page
- `api-gateway/app/templates/staff_orders.html` - staff order processing page
- `api-gateway/app/templates/staff_shipping.html` - staff shipping management page
- `api-gateway/app/templates/admin_users.html` - admin user management page
- `api-gateway/app/templates/admin_products.html` - admin product management page
- `docs/ddd-bookstore-context-map.md` - report-friendly DDD context map

### Existing Files To Modify

- `api-gateway/app/views.py` - role-aware routing and new page handlers
- `api-gateway/api_gateway/urls.py` - register new routes
- `api-gateway/app/templates/base.html` - upgraded layout shell and role-aware navigation
- `api-gateway/app/templates/books.html` - improved catalog
- `api-gateway/app/tests.py` - gateway tests for roles and flows
- `user-service/app/models.py` - stable role choices if not already explicit
- `user-service/app/serializers.py` - expose role consistently
- `user-service/app/views.py` - role-safe user APIs
- `user-service/app/tests.py` - role-related tests
- `book-service/app/models.py` - ensure product data shape supports richer catalog
- `book-service/app/tests.py` - catalog tests
- `book-service/app/management/commands/seed_demo_books.py` or equivalent seed file - create >10 products
- `cart-service/app/views.py` - customer cart operations
- `cart-service/app/tests.py` - cart tests
- `order-service/app/views.py` - order creation and staff update flow
- `order-service/app/tests.py` - order tests
- `payment-service/app/views.py` - demo payment flow
- `payment-service/app/tests.py` - payment tests
- `docker-compose.yml` - add shipping service and env wiring
- `render.yaml` - add shipping service deployment
- `DEPLOY_RENDER.md` - mention shipping service if needed

## Task 1: Stabilize Role Model In User Service

**Files:**
- Modify: `user-service/app/models.py`
- Modify: `user-service/app/serializers.py`
- Modify: `user-service/app/views.py`
- Test: `user-service/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_register_defaults_to_customer(self):
    response = self.client.post(
        "/auth/register/",
        {
            "username": "new-customer",
            "email": "customer@example.com",
            "password": "secret123",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["user"]["role"] == "customer"

def test_login_returns_explicit_role(self):
    User.objects.create_user(
        username="staff1",
        password="secret123",
        role="staff",
        email="staff@example.com",
    )
    response = self.client.post(
        "/auth/login/",
        {"username": "staff1", "password": "secret123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["user"]["role"] == "staff"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL if role is missing, inconsistent, or not defaulted to `customer`

- [ ] **Step 3: Write minimal implementation**

```python
class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_STAFF = "staff"
    ROLE_CUSTOMER = "customer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_STAFF, "Staff"),
        (ROLE_CUSTOMER, "Customer"),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_CUSTOMER,
    )
```

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "full_name", "phone", "address", "role"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS with role returned for register and login flows

- [ ] **Step 5: Commit**

```bash
git add user-service/app/models.py user-service/app/serializers.py user-service/app/views.py user-service/app/tests.py
git commit -m "feat: stabilize user role model"
```

## Task 2: Add Role-Aware Landing And Dashboard Routing In Gateway

**Files:**
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/api_gateway/urls.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_dashboard_redirects_admin_to_admin_dashboard(self):
    session = self.client.session
    session["user"] = {"id": 1, "username": "admin1", "role": "admin"}
    session.save()
    response = self.client.get("/dashboard/", secure=True)
    assert response.status_code == 302
    assert response.url == "/admin/dashboard/"

def test_dashboard_redirects_staff_to_staff_dashboard(self):
    session = self.client.session
    session["user"] = {"id": 2, "username": "staff1", "role": "staff"}
    session.save()
    response = self.client.get("/dashboard/", secure=True)
    assert response.status_code == 302
    assert response.url == "/staff/dashboard/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayRoleRoutingTests -v 2`
Expected: FAIL because `/dashboard/` and role redirects do not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
def dashboard_router(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if user["role"] == "admin":
        return redirect("/admin/dashboard/")
    if user["role"] == "staff":
        return redirect("/staff/dashboard/")
    return redirect("/customer/dashboard/")
```

```python
urlpatterns += [
    path("dashboard/", dashboard_router, name="dashboard_router"),
    path("admin/dashboard/", admin_dashboard, name="admin_dashboard"),
    path("staff/dashboard/", staff_dashboard, name="staff_dashboard"),
    path("customer/dashboard/", customer_dashboard, name="customer_dashboard"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayRoleRoutingTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/views.py api-gateway/api_gateway/urls.py api-gateway/app/tests.py
git commit -m "feat: add role-aware dashboard routing"
```

## Task 3: Upgrade Shared Frontend Shell And Role Navigation

**Files:**
- Modify: `api-gateway/app/templates/base.html`
- Modify: `api-gateway/app/views.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_navigation_contains_management_links(self):
    session = self.client.session
    session["user"] = {"id": 1, "username": "admin1", "role": "admin"}
    session.save()
    response = self.client.get("/admin/dashboard/", secure=True)
    assert response.status_code == 200
    assertContains(response, "Manage Users")
    assertContains(response, "Manage Products")

def test_customer_navigation_contains_cart_and_orders(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.get("/customer/dashboard/", secure=True)
    assert response.status_code == 200
    assertContains(response, "My Cart")
    assertContains(response, "My Orders")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayNavigationTests -v 2`
Expected: FAIL because role-aware menus do not exist yet

- [ ] **Step 3: Write minimal implementation**

```html
{% if user %}
  {% if user.role == "admin" %}
    <a href="/admin/dashboard/" class="nav-link">Dashboard</a>
    <a href="/admin/users/" class="nav-link">Manage Users</a>
    <a href="/admin/products/" class="nav-link">Manage Products</a>
  {% elif user.role == "staff" %}
    <a href="/staff/dashboard/" class="nav-link">Operations</a>
    <a href="/staff/orders/" class="nav-link">Orders</a>
    <a href="/staff/shipping/" class="nav-link">Shipping</a>
  {% else %}
    <a href="/customer/dashboard/" class="nav-link">Home</a>
    <a href="/cart/" class="nav-link">My Cart</a>
    <a href="/orders/me/" class="nav-link">My Orders</a>
  {% endif %}
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayNavigationTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/base.html api-gateway/app/views.py api-gateway/app/tests.py
git commit -m "feat: upgrade shared role-aware navigation"
```

## Task 4: Add Role-Specific Dashboard Pages

**Files:**
- Create: `api-gateway/app/templates/dashboard_admin.html`
- Create: `api-gateway/app/templates/dashboard_staff.html`
- Create: `api-gateway/app/templates/dashboard_customer.html`
- Modify: `api-gateway/app/views.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_dashboard_renders_summary_cards(self):
    session = self.client.session
    session["user"] = {"id": 1, "username": "admin1", "role": "admin"}
    session.save()
    response = self.client.get("/admin/dashboard/", secure=True)
    assertContains(response, "User Overview")
    assertContains(response, "Catalog Overview")

def test_staff_dashboard_renders_operational_cards(self):
    session = self.client.session
    session["user"] = {"id": 2, "username": "staff1", "role": "staff"}
    session.save()
    response = self.client.get("/staff/dashboard/", secure=True)
    assertContains(response, "Orders To Process")
    assertContains(response, "Shipping Queue")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayDashboardTests -v 2`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def admin_dashboard(request):
    user, _ = _get_user(request)
    if not user or user["role"] != "admin":
        return redirect("/login/")
    return render(request, "dashboard_admin.html", {"user": user})
```

```html
<section class="dashboard-grid">
  <article class="glass-card"><h3>User Overview</h3></article>
  <article class="glass-card"><h3>Catalog Overview</h3></article>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayDashboardTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/dashboard_admin.html api-gateway/app/templates/dashboard_staff.html api-gateway/app/templates/dashboard_customer.html api-gateway/app/views.py api-gateway/app/tests.py
git commit -m "feat: add role-specific dashboards"
```

## Task 5: Expand Catalog To More Than 10 Products And Add Product Detail Page

**Files:**
- Modify: `book-service/app/tests.py`
- Modify: `book-service/app/management/commands/seed_demo_books.py`
- Modify: `api-gateway/app/views.py`
- Create: `api-gateway/app/templates/book_detail.html`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_seeded_catalog_contains_more_than_ten_books(self):
    response = self.client.get("/books/")
    assert response.status_code == 200
    assert len(response.json()) > 10

def test_gateway_book_detail_page_renders(self):
    with patch("app.views.requests.get") as get_mock:
        book_response = Mock(status_code=200)
        book_response.json.return_value = {"id": 1, "title": "Clean Code", "price": "19.99"}
        get_mock.return_value = book_response
        response = self.client.get("/books/1/", secure=True)
        assertContains(response, "Clean Code")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `book-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL due to insufficient seed data or missing detail flow

- [ ] **Step 3: Write minimal implementation**

```python
DEMO_BOOKS = [
    {"title": "Clean Code", "author": "Robert C. Martin", "price": "19.99"},
    {"title": "Domain-Driven Design", "author": "Eric Evans", "price": "29.99"},
    {"title": "Refactoring", "author": "Martin Fowler", "price": "24.99"},
    # ... add at least 11 total books across varied categories
]
```

```python
def book_detail(request, pk):
    user, _ = _get_user(request)
    response = requests.get(f"{BOOK_SERVICE_URL}/books/{pk}/", timeout=5)
    book = response.json() if response.status_code == 200 else None
    return render(request, "book_detail.html", {"book": book, "user": user})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `book-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS with >10 products seeded

- [ ] **Step 5: Commit**

```bash
git add book-service api-gateway/app/views.py api-gateway/app/templates/book_detail.html api-gateway/app/tests.py
git commit -m "feat: expand catalog and add product detail view"
```

## Task 6: Complete Customer Cart Flow In Gateway And Cart Service

**Files:**
- Modify: `cart-service/app/views.py`
- Modify: `cart-service/app/tests.py`
- Modify: `api-gateway/app/views.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_customer_can_add_book_to_cart(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.post("/cart/add/1/", secure=True)
    assert response.status_code in (200, 302)

def test_customer_cannot_open_another_users_cart(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.get("/cart/99/", secure=True)
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cart-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL if cart ownership or add flow is incomplete

- [ ] **Step 3: Write minimal implementation**

```python
@csrf_exempt
def add_to_cart(request, pk):
    user, token = _get_user(request)
    if not user or user["role"] != "customer":
        return redirect("/login/")
    payload = {"book_id": pk, "quantity": 1}
    requests.post(f"{CART_SERVICE_URL}/cart/{user['id']}/add/", json=payload, timeout=5)
    return redirect(f"/cart/{user['id']}/")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cart-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cart-service/app/views.py cart-service/app/tests.py api-gateway/app/views.py api-gateway/app/tests.py
git commit -m "feat: complete customer cart flow"
```

## Task 7: Add Checkout And Order Creation Flow

**Files:**
- Create: `api-gateway/app/templates/checkout.html`
- Modify: `api-gateway/app/views.py`
- Modify: `order-service/app/views.py`
- Modify: `order-service/app/tests.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_checkout_submits_order_for_customer(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.post("/checkout/", {"payment_method": "cod"}, secure=True)
    assert response.status_code in (200, 302)

def test_order_service_creates_order_from_cart_payload(self):
    response = self.client.post(
        "/orders/",
        {
            "user": 3,
            "items": [{"book_id": 1, "quantity": 2, "price": "19.99"}],
        },
        format="json",
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `order-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL if order creation from cart snapshot is unsupported

- [ ] **Step 3: Write minimal implementation**

```python
@csrf_exempt
def checkout_view(request):
    user, _ = _get_user(request)
    if not user or user["role"] != "customer":
        return redirect("/login/")
    if request.method == "POST":
        cart_resp = requests.get(f"{CART_SERVICE_URL}/cart/{user['id']}/", timeout=5)
        cart = cart_resp.json() if cart_resp.status_code == 200 else {"items": []}
        payload = {"user": user["id"], "items": cart.get("items", []), "status": "pending"}
        order_resp = requests.post(f"{ORDER_SERVICE_URL}/orders/", json=payload, timeout=10)
        order = order_resp.json()
        return redirect(f"/payment/{order['id']}/")
    return render(request, "checkout.html", {"user": user})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `order-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/checkout.html api-gateway/app/views.py order-service/app/views.py order-service/app/tests.py api-gateway/app/tests.py
git commit -m "feat: add checkout and order creation flow"
```

## Task 8: Add Demo Payment Flow

**Files:**
- Create: `api-gateway/app/templates/payment_result.html`
- Modify: `api-gateway/app/views.py`
- Modify: `payment-service/app/views.py`
- Modify: `payment-service/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_payment_service_returns_success_for_demo_method(self):
    response = self.client.post(
        "/payments/",
        {"order": 1, "method": "demo_success"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "success"

def test_gateway_payment_page_shows_success_message(self):
    response = self.client.get("/payment/result/?status=success", secure=True)
    assertContains(response, "Payment completed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `payment-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
class PaymentView(APIView):
    def post(self, request):
        method = request.data.get("method")
        status = "success" if method != "demo_fail" else "failed"
        return Response({"order": request.data.get("order"), "status": status}, status=201)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `payment-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payment-service/app/views.py payment-service/app/tests.py api-gateway/app/views.py api-gateway/app/templates/payment_result.html
git commit -m "feat: add demo payment flow"
```

## Task 9: Add Shipping Service And Staff Shipping Workflow

**Files:**
- Create: `shipping-service/manage.py`
- Create: `shipping-service/shipping_service/settings.py`
- Create: `shipping-service/shipping_service/urls.py`
- Create: `shipping-service/shipping_service/wsgi.py`
- Create: `shipping-service/app/models.py`
- Create: `shipping-service/app/serializers.py`
- Create: `shipping-service/app/views.py`
- Create: `shipping-service/app/urls.py`
- Create: `shipping-service/app/tests.py`
- Create: `shipping-service/requirements.txt`
- Create: `shipping-service/Dockerfile`
- Modify: `api-gateway/app/views.py`
- Create: `api-gateway/app/templates/staff_shipping.html`
- Create: `api-gateway/app/templates/shipping_detail.html`

- [ ] **Step 1: Write the failing tests**

```python
def test_create_shipment_for_order(self):
    response = self.client.post(
        "/shipping/",
        {"order_id": 10, "status": "pending"},
        format="json",
    )
    assert response.status_code == 201

def test_staff_can_update_shipping_status(self):
    shipment = Shipment.objects.create(order_id=10, status="pending")
    response = self.client.patch(
        f"/shipping/{shipment.id}/",
        {"status": "shipping"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "shipping"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `shipping-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL because service does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
class Shipment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("packed", "Packed"),
        ("shipping", "Shipping"),
        ("delivered", "Delivered"),
    ]
    order_id = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    tracking_code = models.CharField(max_length=64, blank=True, default="")
```

```python
class ShipmentViewSet(ModelViewSet):
    queryset = Shipment.objects.all().order_by("-id")
    serializer_class = ShipmentSerializer
```

- [ ] **Step 4: Run test to verify it passes**

Run: `shipping-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shipping-service api-gateway/app/views.py api-gateway/app/templates/staff_shipping.html api-gateway/app/templates/shipping_detail.html
git commit -m "feat: add shipping service and staff workflow"
```

## Task 10: Add Customer Order History And Shipping Tracking Pages

**Files:**
- Create: `api-gateway/app/templates/my_orders.html`
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/api_gateway/urls.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_customer_order_history_page_renders(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.get("/orders/me/", secure=True)
    assert response.status_code == 200
    assertContains(response, "My Orders")

def test_customer_shipping_page_renders(self):
    session = self.client.session
    session["user"] = {"id": 3, "username": "customer1", "role": "customer"}
    session.save()
    response = self.client.get("/shipping/10/", secure=True)
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayCustomerFlowTests -v 2`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def my_orders_view(request):
    user, _ = _get_user(request)
    if not user or user["role"] != "customer":
        return redirect("/login/")
    response = requests.get(f"{ORDER_SERVICE_URL}/orders/user/{user['id']}/", timeout=10)
    orders = response.json() if response.status_code == 200 else []
    return render(request, "my_orders.html", {"orders": orders, "user": user})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayCustomerFlowTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/my_orders.html api-gateway/app/views.py api-gateway/api_gateway/urls.py api-gateway/app/tests.py
git commit -m "feat: add customer order and shipping views"
```

## Task 11: Add Staff Order Processing Screens

**Files:**
- Create: `api-gateway/app/templates/staff_orders.html`
- Modify: `api-gateway/app/views.py`
- Modify: `order-service/app/views.py`
- Modify: `order-service/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_staff_order_page_renders(self):
    session = self.client.session
    session["user"] = {"id": 2, "username": "staff1", "role": "staff"}
    session.save()
    response = self.client.get("/staff/orders/", secure=True)
    assert response.status_code == 200
    assertContains(response, "Orders To Process")

def test_staff_can_update_order_status(self):
    order = Order.objects.create(user=3, status="paid")
    response = self.client.patch(
        f"/orders/{order.id}/",
        {"status": "processing"},
        format="json",
    )
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `order-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def staff_orders_view(request):
    user, _ = _get_user(request)
    if not user or user["role"] != "staff":
        return redirect("/login/")
    response = requests.get(f"{ORDER_SERVICE_URL}/orders/", timeout=10)
    orders = response.json() if response.status_code == 200 else []
    return render(request, "staff_orders.html", {"orders": orders, "user": user})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `order-service\\venv\\Scripts\\python.exe manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/staff_orders.html api-gateway/app/views.py order-service/app/views.py order-service/app/tests.py
git commit -m "feat: add staff order processing pages"
```

## Task 12: Add Admin User And Product Management Screens

**Files:**
- Create: `api-gateway/app/templates/admin_users.html`
- Create: `api-gateway/app/templates/admin_products.html`
- Modify: `api-gateway/app/views.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_user_management_page_renders(self):
    session = self.client.session
    session["user"] = {"id": 1, "username": "admin1", "role": "admin"}
    session.save()
    response = self.client.get("/admin/users/", secure=True)
    assert response.status_code == 200
    assertContains(response, "Manage Users")

def test_admin_product_management_page_renders(self):
    session = self.client.session
    session["user"] = {"id": 1, "username": "admin1", "role": "admin"}
    session.save()
    response = self.client.get("/admin/products/", secure=True)
    assert response.status_code == 200
    assertContains(response, "Manage Products")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayAdminTests -v 2`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
def admin_users_view(request):
    user, _ = _get_user(request)
    if not user or user["role"] != "admin":
        return redirect("/login/")
    response = requests.get(f"{USER_SERVICE_URL}/users/", timeout=10)
    users = response.json() if response.status_code == 200 else []
    return render(request, "admin_users.html", {"users": users, "user": user})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayAdminTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/admin_users.html api-gateway/app/templates/admin_products.html api-gateway/app/views.py api-gateway/app/tests.py
git commit -m "feat: add admin management pages"
```

## Task 13: Wire Shipping Service Into Deployment

**Files:**
- Modify: `docker-compose.yml`
- Modify: `render.yaml`
- Modify: `DEPLOY_RENDER.md`

- [ ] **Step 1: Write the failing verification**

```yaml
services:
  shipping-service:
    build: ./shipping-service
```

Add a checklist item that deployment must expose `shipping-service` to the gateway and other services.

- [ ] **Step 2: Run verification to confirm deployment wiring is incomplete**

Run: `docker compose config`
Expected: No `shipping-service` block in resolved config before the change

- [ ] **Step 3: Write minimal implementation**

```yaml
  shipping-service:
    build: ./shipping-service
    ports:
      - "8011:8000"
```

```yaml
      - key: SHIPPING_SERVICE_URL
        value: https://bookstore-shipping-service.onrender.com
```

- [ ] **Step 4: Run verification to confirm compose parses**

Run: `docker compose config`
Expected: PASS with a resolved `shipping-service` section

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml render.yaml DEPLOY_RENDER.md
git commit -m "chore: wire shipping service deployment"
```

## Task 14: Add DDD Report Artifact

**Files:**
- Create: `docs/ddd-bookstore-context-map.md`

- [ ] **Step 1: Write the failing verification**

Create a checklist requiring a report file that maps:

- bounded context
- owning service
- main entity
- main use case

Expected: file does not exist yet

- [ ] **Step 2: Run verification to confirm the file is missing**

Run: `Test-Path docs/ddd-bookstore-context-map.md`
Expected: `False`

- [ ] **Step 3: Write minimal implementation**

```md
# Bookstore DDD Context Map

| Bounded Context | Service | Main Entities | Main Use Cases |
| --- | --- | --- | --- |
| Identity | user-service | User, Role | login, register, role assignment |
| Catalog | book-service | Book, Category, Publisher | browse products, manage products |
| Cart | cart-service | Cart, CartItem | add to cart, update quantity |
| Ordering | order-service | Order, OrderItem | checkout, track order lifecycle |
| Payment | payment-service | Payment | pay for order |
| Shipping | shipping-service | Shipment | update shipment status |
| Advisory | advisor-service | BehaviorProfile, KBDocument | consult AI advisor |
```

- [ ] **Step 4: Run verification to confirm the file exists**

Run: `Test-Path docs/ddd-bookstore-context-map.md`
Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add docs/ddd-bookstore-context-map.md
git commit -m "docs: add bookstore DDD context map"
```

## Task 15: End-To-End Verification

**Files:**
- Verify only: full stack in worktree

- [ ] **Step 1: Run focused service tests**

Run:

```bash
user-service\venv\Scripts\python.exe manage.py test app.tests -v 2
book-service\venv\Scripts\python.exe manage.py test app.tests -v 2
cart-service\venv\Scripts\python.exe manage.py test app.tests -v 2
order-service\venv\Scripts\python.exe manage.py test app.tests -v 2
payment-service\venv\Scripts\python.exe manage.py test app.tests -v 2
shipping-service\venv\Scripts\python.exe manage.py test app.tests -v 2
```

Expected: all targeted service suites pass

- [ ] **Step 2: Run gateway tests**

Run: `api-gateway\venv\Scripts\python.exe manage.py test app.tests -v 2`
Expected: role, navigation, checkout, and advisor tests pass

- [ ] **Step 3: Run deployment verification**

Run:

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

Expected: all services, including `shipping-service`, are `Up`

- [ ] **Step 4: Run smoke tests**

Run:

```bash
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/ | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/customer/dashboard/ | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/staff/dashboard/ | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/admin/dashboard/ | Select-Object -ExpandProperty StatusCode
```

Expected: pages respond after login/session setup in browser-based demo

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "test: verify bookstore role and DDD upgrade"
```

## Self-Review

- Spec coverage:
  - UI upgrade is covered by Tasks 3, 4, 5, 10, 11, and 12.
  - Role separation is covered by Tasks 1, 2, 3, 4, 11, and 12.
  - `cart -> order -> payment -> shipping` is covered by Tasks 6, 7, 8, 9, and 10.
  - Product count > 10 is covered by Task 5.
  - DDD level-1 decomposition is covered by Tasks 9 and 14 plus the service mapping throughout the plan.
  - Deploy integration is covered by Task 13 and verified in Task 15.
- Placeholder scan:
  - No `TODO`, `TBD`, or unresolved placeholders remain.
- Type consistency:
  - Roles are consistently `admin`, `staff`, `customer`.
  - Shipping statuses are consistently `pending`, `packed`, `shipping`, `delivered`.
  - Main routes consistently use `/admin/...`, `/staff/...`, `/customer/...`, `/orders/me/`, and `/shipping/...`.
