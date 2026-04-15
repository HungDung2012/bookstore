import json
import os
from decimal import Decimal

import requests
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


USER_SERVICE_URL = _service_url("USER_SERVICE_URL", "user-service:8000")
BOOK_SERVICE_URL = _service_url("BOOK_SERVICE_URL", "book-service:8000")
INVENTORY_SERVICE_URL = _service_url("INVENTORY_SERVICE_URL", "inventory-service:8000")
CART_SERVICE_URL = _service_url("CART_SERVICE_URL", "cart-service:8000")
ORDER_SERVICE_URL = _service_url("ORDER_SERVICE_URL", "order-service:8000")
PAYMENT_SERVICE_URL = _service_url("PAYMENT_SERVICE_URL", "payment-service:8000")
REVIEW_SERVICE_URL = _service_url("REVIEW_SERVICE_URL", "review-service:8000")
NOTIFICATION_SERVICE_URL = _service_url("NOTIFICATION_SERVICE_URL", "notification-service:8000")
ADVISOR_SERVICE_URL = _service_url("ADVISOR_SERVICE_URL", "advisor-service:8000")
SHIPPING_SERVICE_URL = _service_url("SHIPPING_SERVICE_URL", "shipping-service:8000")
STAFF_ORDER_STATUS_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["paid", "cancelled"],
}
SHIPPING_STATUS_OPTIONS = ["pending", "packed", "shipping", "delivered"]
SHIPPING_STATUS_TRANSITIONS = {
    "pending": {"packed"},
    "packed": {"shipping"},
    "shipping": {"delivered"},
    "delivered": set(),
}


def _dashboard_path_for_role(role):
    dashboard_paths = {
        "admin": "/admin/dashboard/",
        "staff": "/staff/dashboard/",
        "customer": "/customer/dashboard/",
    }
    return dashboard_paths.get(role, "/login/")


def _get_user(request):
    token = request.session.get("token")
    user = request.session.get("user")
    if token and user:
        return user, token

    if token:
        try:
            verify_resp = requests.post(
                f"{USER_SERVICE_URL}/auth/verify/",
                json={"token": token},
                timeout=5,
            )
            if verify_resp.status_code == 200:
                user = verify_resp.json().get("user")
                if user:
                    request.session["user"] = user
                    request.session.modified = True
                    return user, token
        except requests.exceptions.RequestException:
            pass

    return None, None


def _require_matching_user(request, resource_user_id):
    user, token = _get_user(request)
    if not user:
        return None, None, redirect("/login/")
    if user["id"] != resource_user_id:
        return user, token, HttpResponseForbidden("You cannot access another user's data.")
    return user, token, None


def _upstream_error(response, fallback):
    try:
        payload = response.json()
    except ValueError:
        return fallback

    if isinstance(payload, dict):
        return payload.get("error", fallback)
    return fallback


def _shipping_for_order(order_id):
    try:
        response = requests.get(
            f"{SHIPPING_SERVICE_URL}/shipping/",
            params={"order_id": order_id},
            timeout=5,
        )
        if response.status_code != 200:
            return None
        shipments = response.json()
        if isinstance(shipments, list) and shipments:
            return shipments[0]
    except requests.exceptions.RequestException:
        pass
    return None


def _order_service_internal_headers():
    return {
        "X-Internal-Service-Token": os.getenv("ORDER_SERVICE_INTERNAL_TOKEN", "gateway-internal-token"),
    }


def _sync_order_status_for_shipping(order_id, shipment_status):
    order_status = {"shipping": "shipping", "delivered": "delivered"}.get(shipment_status)
    if not order_status:
        return

    return requests.put(
        f"{ORDER_SERVICE_URL}/orders/{order_id}/status/",
        json={"status": order_status},
        headers=_order_service_internal_headers(),
        timeout=5,
    )


def _load_order(order_id):
    try:
        response = requests.get(f"{ORDER_SERVICE_URL}/orders/{order_id}/", timeout=5)
    except requests.exceptions.RequestException:
        return None, None

    if response.status_code != 200:
        return None, response

    try:
        return response.json(), response
    except ValueError:
        return None, response


def _can_transition_shipment(current_status, next_status):
    return next_status == current_status or next_status in SHIPPING_STATUS_TRANSITIONS.get(current_status, set())


def _order_ready_for_shipment_status(order_status, current_shipment_status, next_shipment_status):
    required_status = {
        ("packed", "shipping"): "paid",
        ("shipping", "delivered"): "shipping",
    }.get((current_shipment_status, next_shipment_status))
    if required_status is None:
        return True
    return order_status == required_status


def _rollback_shipment_status(shipment_id, previous_status):
    try:
        return requests.patch(
            f"{SHIPPING_SERVICE_URL}/shipping/{shipment_id}/",
            json={"status": previous_status},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        return None


def _create_shipping_error_context(user, error):
    try:
        order_response = requests.get(f"{ORDER_SERVICE_URL}/orders/", timeout=5)
        orders = order_response.json() if order_response.status_code == 200 else []
    except requests.exceptions.RequestException:
        orders = []
        if error is None:
            error = "Order service unavailable."

    try:
        shipment_response = requests.get(f"{SHIPPING_SERVICE_URL}/shipping/", timeout=5)
        shipments = shipment_response.json() if shipment_response.status_code == 200 else []
    except requests.exceptions.RequestException:
        shipments = []
        if error is None:
            error = "Shipping service unavailable."

    shipment_by_order_id = {shipment["order_id"]: shipment for shipment in shipments if "order_id" in shipment}
    managed_orders = []
    for order in orders:
        if order.get("status") == "cancelled":
            continue
        order["shipment"] = shipment_by_order_id.get(order.get("id"))
        order["can_create_shipment"] = order.get("status") == "paid" and not order["shipment"]
        managed_orders.append(order)

    return {
        "user": user,
        "orders": managed_orders,
        "shipments": shipments,
        "error": error,
    }


def _create_staff_orders_context(user, error=None):
    try:
        response = requests.get(f"{ORDER_SERVICE_URL}/orders/", timeout=5)
        orders = response.json() if response.status_code == 200 else []
    except requests.exceptions.RequestException:
        orders = []
        if error is None:
            error = "Order service unavailable."

    managed_orders = []
    for order in orders:
        next_statuses = STAFF_ORDER_STATUS_TRANSITIONS.get(order.get("status"))
        if not next_statuses:
            continue
        order["next_statuses"] = next_statuses
        managed_orders.append(order)

    return {
        "user": user,
        "orders": managed_orders,
        "error": error,
    }


def _render_staff_shipping_error(request, user, error):
    return render(request, "staff_shipping.html", _create_shipping_error_context(user, error))


def _render_shipping_detail(request, user, order, shipment, error):
    return render(
        request,
        "shipping_detail.html",
        {
            "user": user,
            "order": order,
            "shipment": shipment,
            "shipping_status_options": SHIPPING_STATUS_OPTIONS,
            "error": error,
        },
    )


def health_check(request):
    return JsonResponse({"status": "ok", "service": "api-gateway"})


@csrf_exempt
def login_view(request):
    if request.method == "POST":
        data = {
            "username": request.POST.get("username"),
            "password": request.POST.get("password"),
        }
        try:
            response = requests.post(f"{USER_SERVICE_URL}/auth/login/", json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                request.session.cycle_key()
                request.session["token"] = result["token"]
                request.session["user"] = result["user"]
                request.session.modified = True
                return redirect("/books/")
            error = response.json().get("error", "Login failed")
        except requests.exceptions.RequestException as exc:
            error = f"User service unavailable: {exc}"
        return render(request, "login.html", {"error": error})
    return render(request, "login.html")


@csrf_exempt
def register_view(request):
    if request.method == "POST":
        data = {
            "username": request.POST.get("username"),
            "email": request.POST.get("email"),
            "password": request.POST.get("password"),
            "full_name": request.POST.get("full_name", ""),
            "phone": request.POST.get("phone", ""),
            "address": request.POST.get("address", ""),
        }
        try:
            response = requests.post(f"{USER_SERVICE_URL}/auth/register/", json=data, timeout=5)
            if response.status_code == 201:
                result = response.json()
                request.session.cycle_key()
                request.session["token"] = result["token"]
                request.session["user"] = result["user"]
                request.session.modified = True
                return redirect("/books/")
            error = response.json()
        except requests.exceptions.RequestException as exc:
            error = f"User service unavailable: {exc}"
        return render(request, "register.html", {"error": error})
    return render(request, "register.html")


def logout_view(request):
    request.session.flush()
    return redirect("/login/")


def dashboard_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    return redirect(_dashboard_path_for_role(user.get("role")))


def role_dashboard_view(request, role):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")

    target = _dashboard_path_for_role(user.get("role"))
    if request.path != target:
        return redirect(target)
    admin_sections = {
        "overview": {
            "page_title": "Admin dashboard",
            "page_description": "Track platform health, user activity, and catalog readiness from one place.",
        },
        "users": {
            "page_title": "Manage Users",
            "page_description": "Review user activity, access requests, and account health before issues escalate.",
        },
        "products": {
            "page_title": "Manage Products",
            "page_description": "Keep the catalog aligned with merchandising priorities, stock updates, and content quality.",
        },
    }
    dashboards = {
        "admin": {
            "template_name": "dashboard_admin.html",
        },
        "staff": {
            "template_name": "dashboard_staff.html",
            "page_title": "Staff dashboard",
            "page_description": "Stay on top of daily fulfillment, shipping, and inventory operations.",
        },
        "customer": {
            "template_name": "dashboard_customer.html",
            "page_title": "Customer dashboard",
            "page_description": "Pick up where you left off with recommendations, orders, and account activity.",
        },
    }
    dashboard = dashboards.get(role)
    if not dashboard:
        return redirect("/login/")

    context = {
        "user": user,
        "page_title": dashboard.get("page_title"),
        "page_description": dashboard.get("page_description"),
    }
    if role == "admin":
        section = request.GET.get("section")
        if section not in {"users", "products"}:
            section = "overview"
        context["admin_section"] = section
        context["page_title"] = admin_sections[section]["page_title"]
        context["page_description"] = admin_sections[section]["page_description"]

    return render(
        request,
        dashboard["template_name"],
        context,
    )


def profile_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    return render(request, "profile.html", {"user": user})


def book_list(request):
    user, _ = _get_user(request)
    try:
        response = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
        response.raise_for_status()
        books = response.json()
        for book in books:
            try:
                rating_resp = requests.get(
                    f"{REVIEW_SERVICE_URL}/reviews/rating/{book['id']}/",
                    timeout=3,
                )
                if rating_resp.status_code == 200:
                    book["rating"] = rating_resp.json()
            except requests.exceptions.RequestException:
                pass
    except requests.exceptions.RequestException:
        books = []
    return render(request, "books.html", {"books": books, "user": user})


@csrf_exempt
def book_create(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")

    categories, publishers = [], []
    try:
        cat_resp = requests.get(f"{BOOK_SERVICE_URL}/categories/", timeout=5)
        if cat_resp.status_code == 200:
            categories = cat_resp.json()
        pub_resp = requests.get(f"{BOOK_SERVICE_URL}/publishers/", timeout=5)
        if pub_resp.status_code == 200:
            publishers = pub_resp.json()
    except requests.exceptions.RequestException:
        pass

    if request.method == "POST":
        data = {
            "title": request.POST.get("title"),
            "author": request.POST.get("author"),
            "price": request.POST.get("price"),
            "stock": request.POST.get("stock"),
        }
        category = request.POST.get("category")
        publisher = request.POST.get("publisher")
        if category:
            data["category"] = int(category)
        if publisher:
            data["publisher"] = int(publisher)
        try:
            response = requests.post(f"{BOOK_SERVICE_URL}/books/", json=data, timeout=5)
            if response.status_code == 201:
                return redirect("/books/")
            error = response.json()
        except requests.exceptions.RequestException as exc:
            error = {"error": str(exc)}
        return render(
            request,
            "book_form.html",
            {
                "error": error,
                "categories": categories,
                "publishers": publishers,
                "user": user,
            },
        )

    return render(
        request,
        "book_form.html",
        {"categories": categories, "publishers": publishers, "user": user},
    )


@csrf_exempt
def book_edit(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")

    categories, publishers, book = [], [], {}
    try:
        book_resp = requests.get(f"{BOOK_SERVICE_URL}/books/{pk}/", timeout=5)
        if book_resp.status_code == 200:
            book = book_resp.json()
        cat_resp = requests.get(f"{BOOK_SERVICE_URL}/categories/", timeout=5)
        if cat_resp.status_code == 200:
            categories = cat_resp.json()
        pub_resp = requests.get(f"{BOOK_SERVICE_URL}/publishers/", timeout=5)
        if pub_resp.status_code == 200:
            publishers = pub_resp.json()
    except requests.exceptions.RequestException:
        pass

    if request.method == "POST":
        data = {
            "title": request.POST.get("title"),
            "author": request.POST.get("author"),
            "price": request.POST.get("price"),
            "stock": request.POST.get("stock"),
            "category": int(request.POST.get("category")) if request.POST.get("category") else None,
            "publisher": int(request.POST.get("publisher")) if request.POST.get("publisher") else None,
        }
        try:
            response = requests.put(f"{BOOK_SERVICE_URL}/books/{pk}/", json=data, timeout=5)
            if response.status_code == 200:
                return redirect("/books/")
            error = response.json()
        except requests.exceptions.RequestException as exc:
            error = {"error": str(exc)}
        return render(
            request,
            "book_form.html",
            {
                "error": error,
                "book": book,
                "categories": categories,
                "publishers": publishers,
                "editing": True,
                "user": user,
            },
        )

    return render(
        request,
        "book_form.html",
        {
            "book": book,
            "categories": categories,
            "publishers": publishers,
            "editing": True,
            "user": user,
        },
    )


@csrf_exempt
def book_delete(request, pk):
    if request.method == "POST":
        try:
            requests.delete(f"{BOOK_SERVICE_URL}/books/{pk}/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect("/books/")


def book_detail(request, pk):
    user, _ = _get_user(request)
    book, reviews, rating = {}, [], {}
    try:
        book_resp = requests.get(f"{BOOK_SERVICE_URL}/books/{pk}/", timeout=5)
        if book_resp.status_code == 200:
            book = book_resp.json()
            try:
                category_resp = requests.get(f"{BOOK_SERVICE_URL}/categories/", timeout=5)
                if category_resp.status_code == 200:
                    categories = {item["id"]: item["name"] for item in category_resp.json()}
                    book["category_name"] = categories.get(book.get("category"))
                publisher_resp = requests.get(f"{BOOK_SERVICE_URL}/publishers/", timeout=5)
                if publisher_resp.status_code == 200:
                    publishers = {item["id"]: item["name"] for item in publisher_resp.json()}
                    book["publisher_name"] = publishers.get(book.get("publisher"))
            except requests.exceptions.RequestException:
                pass
        review_resp = requests.get(f"{REVIEW_SERVICE_URL}/reviews/?book_id={pk}", timeout=5)
        if review_resp.status_code == 200:
            reviews = review_resp.json()
        rating_resp = requests.get(f"{REVIEW_SERVICE_URL}/reviews/rating/{pk}/", timeout=3)
        if rating_resp.status_code == 200:
            rating = rating_resp.json()
        for review in reviews:
            try:
                user_resp = requests.get(
                    f"{USER_SERVICE_URL}/users/{review['user_id']}/",
                    timeout=3,
                )
                if user_resp.status_code == 200:
                    payload = user_resp.json()
                    review["username"] = payload.get("full_name") or payload.get("username")
            except requests.exceptions.RequestException:
                review["username"] = f"User #{review['user_id']}"
    except requests.exceptions.RequestException:
        pass

    return render(
        request,
        "book_detail.html",
        {"book": book, "reviews": reviews, "rating": rating, "user": user},
    )


@csrf_exempt
def add_review(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if request.method == "POST":
        data = {
            "book_id": pk,
            "user_id": user["id"],
            "rating": int(request.POST.get("rating", 5)),
            "title": request.POST.get("title", ""),
            "comment": request.POST.get("comment", ""),
        }
        try:
            requests.post(f"{REVIEW_SERVICE_URL}/reviews/", json=data, timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/books/{pk}/")


@csrf_exempt
def add_to_cart(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if request.method == "POST":
        book_id = request.POST.get("book_id")
        quantity = request.POST.get("quantity", 1)
        user_id = user["id"]
        try:
            cart_resp = requests.get(f"{CART_SERVICE_URL}/carts/{user_id}/", timeout=5)
            if cart_resp.status_code != 200:
                requests.post(f"{CART_SERVICE_URL}/carts/", json={"customer_id": user_id}, timeout=5)
        except requests.exceptions.RequestException:
            try:
                requests.post(f"{CART_SERVICE_URL}/carts/", json={"customer_id": user_id}, timeout=5)
            except requests.exceptions.RequestException:
                pass
        try:
            requests.post(
                f"{CART_SERVICE_URL}/cart-items/",
                json={"customer_id": user_id, "book_id": int(book_id), "quantity": int(quantity)},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/cart/{user['id']}/")


def view_cart(request, customer_id):
    user, _, response = _require_matching_user(request, customer_id)
    if response:
        return response

    try:
        cart_resp = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
        cart_resp.raise_for_status()
        items = cart_resp.json()
        try:
            book_resp = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            if book_resp.status_code == 200:
                books = {book["id"]: book for book in book_resp.json()}
                for item in items:
                    book_id = item.get("book_id")
                    if book_id in books:
                        item["book_title"] = books[book_id].get("title")
                        item["book_price"] = books[book_id].get("price")
        except requests.exceptions.RequestException:
            pass
    except requests.exceptions.RequestException:
        items = []

    return render(request, "cart.html", {"items": items, "customer_id": customer_id, "user": user})


def _checkout_context_for_user(user):
    try:
        cart_resp = requests.get(f"{CART_SERVICE_URL}/carts/{user['id']}/", timeout=5)
        if cart_resp.status_code != 200:
            return {"items": [], "total_amount": "0.00", "error": "Cart not found or empty"}
        cart_items = cart_resp.json()
    except requests.exceptions.RequestException as exc:
        return {"items": [], "total_amount": "0.00", "error": f"Cart service unavailable: {exc}"}

    if not cart_items:
        return {"items": [], "total_amount": "0.00", "error": "Your cart is empty"}

    books = {}
    if any("book_title" not in item or "book_price" not in item for item in cart_items):
        try:
            books_resp = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            books_resp.raise_for_status()
            books = {book["id"]: book for book in books_resp.json()}
        except requests.exceptions.RequestException as exc:
            return {"items": [], "total_amount": "0.00", "error": f"Book service unavailable: {exc}"}

    checkout_items = []
    total_amount = Decimal("0.00")
    for item in cart_items:
        book_title = item.get("book_title")
        unit_price_value = item.get("book_price")
        if book_title is None or unit_price_value is None:
            book = books.get(item.get("book_id"))
            if not book:
                return {"items": [], "total_amount": "0.00", "error": f"Book {item.get('book_id')} not found"}
            book_title = book["title"]
            unit_price_value = book["price"]

        unit_price = Decimal(str(unit_price_value))
        quantity = int(item["quantity"])
        checkout_items.append(
            {
                "book_id": item["book_id"],
                "quantity": quantity,
                "book_title": book_title,
                "unit_price": f"{unit_price:.2f}",
                "subtotal": f"{(unit_price * quantity):.2f}",
            }
        )
        total_amount += unit_price * quantity

    return {
        "items": checkout_items,
        "total_amount": f"{total_amount:.2f}",
        "error": None,
    }


@csrf_exempt
def update_cart_item(request, customer_id):
    user, _, response = _require_matching_user(request, customer_id)
    if response:
        return response

    if request.method == "POST":
        book_id = request.POST.get("book_id")
        quantity = request.POST.get("quantity")
        try:
            requests.put(
                f"{CART_SERVICE_URL}/carts/{customer_id}/update-item/",
                json={"book_id": int(book_id), "quantity": int(quantity)},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/cart/{user['id']}/")


@csrf_exempt
def delete_cart_item(request, customer_id, item_id):
    user, _, response = _require_matching_user(request, customer_id)
    if response:
        return response

    if request.method == "POST":
        try:
            requests.delete(f"{CART_SERVICE_URL}/carts/{customer_id}/delete-item/{item_id}/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/cart/{user['id']}/")


@csrf_exempt
def checkout(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    checkout_context = _checkout_context_for_user(user)
    if request.method == "POST":
        if checkout_context["error"]:
            return render(request, "checkout.html", {"error": checkout_context["error"], "user": user, **checkout_context})

        data = {
            "user_id": user["id"],
            "shipping_name": request.POST.get("shipping_name"),
            "shipping_phone": request.POST.get("shipping_phone"),
            "shipping_address": request.POST.get("shipping_address"),
            "note": request.POST.get("note", ""),
            "payment_method": request.POST.get("payment_method", "cod"),
            "items": [
                {
                    "book_id": item["book_id"],
                    "quantity": item["quantity"],
                    "book_title": item["book_title"],
                    "unit_price": item["unit_price"],
                }
                for item in checkout_context["items"]
            ],
        }
        try:
            response = requests.post(f"{ORDER_SERVICE_URL}/orders/", json=data, timeout=10)
            if response.status_code == 201:
                order = response.json()
                if data["payment_method"] in {"demo_success", "demo_fail"}:
                    payment_payload = {
                        "order_id": order["id"],
                        "amount": checkout_context["total_amount"],
                        "method": data["payment_method"],
                    }
                    payment_message = "Payment completed."
                    payment = None
                    payment_status = "completed"
                    try:
                        payment_response = requests.post(
                            f"{PAYMENT_SERVICE_URL}/payments/",
                            json=payment_payload,
                            timeout=10,
                        )
                        try:
                            payment_data = payment_response.json()
                        except ValueError:
                            payment_data = {}
                        payment = payment_data.get("payment")
                        payment_message = payment_data.get("message", payment_message)
                        payment_status = (
                            payment.get("status")
                            if isinstance(payment, dict) and payment.get("status")
                            else "failed"
                        )
                    except requests.exceptions.RequestException as exc:
                        payment_message = f"Demo payment could not be processed: {exc}"
                        payment_status = "failed"

                    return render(
                        request,
                        "payment_result.html",
                        {
                            "user": user,
                            "order": order,
                            "payment": payment,
                            "payment_status": payment_status,
                            "message": payment_message,
                        },
                    )
                return redirect(f"/orders/{order['id']}/")
            error = response.json().get("error", "Checkout failed")
            return render(request, "checkout.html", {"error": error, "user": user, **checkout_context})
        except requests.exceptions.RequestException as exc:
            return render(request, "checkout.html", {"error": str(exc), "user": user, **checkout_context})

    return render(request, "checkout.html", {"user": user, **checkout_context})


def order_list(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        response = requests.get(f"{ORDER_SERVICE_URL}/orders/?user_id={user['id']}", timeout=5)
        orders = response.json() if response.status_code == 200 else []
    except requests.exceptions.RequestException:
        orders = []
    return render(request, "my_orders.html", {"orders": orders, "user": user})


def order_detail(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        response = requests.get(f"{ORDER_SERVICE_URL}/orders/{pk}/", timeout=5)
        order = response.json() if response.status_code == 200 else {}
    except requests.exceptions.RequestException:
        order = {}

    if order and order.get("user_id") != user["id"]:
        return HttpResponseForbidden("You cannot access another user's order.")

    return render(request, "order_detail.html", {"order": order, "user": user})


@csrf_exempt
def staff_orders_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if user.get("role") != "staff":
        return redirect(_dashboard_path_for_role(user.get("role")))

    error = None
    if request.method == "POST":
        try:
            order_id = int(request.POST.get("order_id", ""))
        except (TypeError, ValueError):
            error = "A valid order is required."
        else:
            try:
                order, order_response = _load_order(order_id)
                if order is None:
                    if order_response and order_response.status_code == 404:
                        error = "Order not found."
                    else:
                        error = "Order service could not verify this order."
                else:
                    allowed_statuses = STAFF_ORDER_STATUS_TRANSITIONS.get(order.get("status"), [])
                    next_status = request.POST.get("status")
                    if next_status not in allowed_statuses:
                        error = "Select a valid staff order status."
                    else:
                        response = requests.put(
                            f"{ORDER_SERVICE_URL}/orders/{order_id}/status/",
                            json={"status": next_status},
                            headers=_order_service_internal_headers(),
                            timeout=5,
                        )
                        if response.status_code == 200:
                            return redirect("/staff/orders/")
                        error = _upstream_error(response, "Order service rejected the status update.")
            except requests.exceptions.RequestException as exc:
                error = f"Order service unavailable: {exc}"

    return render(request, "staff_orders.html", _create_staff_orders_context(user, error))


@csrf_exempt
def staff_shipping_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if user.get("role") != "staff":
        return redirect(_dashboard_path_for_role(user.get("role")))

    error = None
    if request.method == "POST":
        try:
            order_id = int(request.POST.get("order_id", ""))
        except (TypeError, ValueError):
            error = "A valid order is required to create a shipment."
        else:
            order, order_response = _load_order(order_id)
            if order is None:
                if order_response and order_response.status_code == 404:
                    error = "Order not found."
                else:
                    error = "Order service could not verify this order."
                return _render_staff_shipping_error(request, user, error)

            if order.get("status") == "cancelled":
                error = "Cancelled orders cannot receive shipments."
                return _render_staff_shipping_error(request, user, error)

            if order.get("status") != "paid":
                error = "Only paid orders can be moved into shipping."
                return _render_staff_shipping_error(request, user, error)

            existing_shipment = _shipping_for_order(order_id)
            if existing_shipment:
                return redirect(f"/shipping/{order_id}/")

            try:
                response = requests.post(
                    f"{SHIPPING_SERVICE_URL}/shipping/",
                    json={"order_id": order_id, "status": "pending"},
                    timeout=5,
                )
                if response.status_code in {200, 201}:
                    return redirect(f"/shipping/{order_id}/")
                error = _upstream_error(response, "Shipping service rejected shipment creation.")
            except requests.exceptions.RequestException as exc:
                error = f"Shipping service unavailable: {exc}"
    return render(request, "staff_shipping.html", _create_shipping_error_context(user, error))


@csrf_exempt
def shipping_detail(request, order_id):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if user.get("role") not in {"staff", "customer"}:
        return redirect(_dashboard_path_for_role(user.get("role")))

    error = None
    order, order_response = _load_order(order_id)

    if user.get("role") == "customer" and order is None:
        return HttpResponseNotFound("Shipment not found.")

    if order and user.get("role") == "customer" and order.get("user_id") != user["id"]:
        return HttpResponseForbidden("You cannot access another user's shipment.")

    if order is None:
        error = "Order service unavailable."
        order = {}

    shipment = _shipping_for_order(order_id)

    if request.method == "POST" and user.get("role") == "staff" and shipment:
        next_status = request.POST.get("status")
        if next_status not in SHIPPING_STATUS_OPTIONS:
            error = "Select a valid shipping status."
        elif not _can_transition_shipment(shipment["status"], next_status):
            error = "Invalid shipping status transition."
        elif not _order_ready_for_shipment_status(order.get("status"), shipment["status"], next_status):
            error = "Order is not ready for this shipping update."
        elif next_status == shipment["status"]:
            return redirect(f"/shipping/{order_id}/")
        else:
            previous_status = shipment["status"]
            try:
                response = requests.patch(
                    f"{SHIPPING_SERVICE_URL}/shipping/{shipment['id']}/",
                    json={"status": next_status},
                    timeout=5,
                )
                if response.status_code == 200:
                    order_sync_response = _sync_order_status_for_shipping(order_id, next_status)
                    if order_sync_response is None:
                        return redirect(f"/shipping/{order_id}/")
                    if order_sync_response.status_code != 200:
                        rollback_response = _rollback_shipment_status(shipment["id"], previous_status)
                        if rollback_response is not None and rollback_response.status_code == 200:
                            error = "Order status sync failed. Shipment change was rolled back."
                        else:
                            error = "Order status sync failed and shipment rollback may be required."
                    else:
                        return redirect(f"/shipping/{order_id}/")
                else:
                    error = _upstream_error(response, "Shipping service rejected the status update.")
            except requests.exceptions.RequestException as exc:
                error = f"Shipping service unavailable: {exc}"
            shipment = _shipping_for_order(order_id)

    return _render_shipping_detail(request, user, order, shipment, error)


@csrf_exempt
def cancel_order(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if request.method == "POST":
        try:
            order_resp = requests.get(f"{ORDER_SERVICE_URL}/orders/{pk}/", timeout=5)
            if order_resp.status_code == 200 and order_resp.json().get("user_id") != user["id"]:
                return HttpResponseForbidden("You cannot cancel another user's order.")
        except requests.exceptions.RequestException:
            pass
        try:
            requests.post(f"{ORDER_SERVICE_URL}/orders/{pk}/cancel/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/orders/{pk}/")


def notifications_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        response = requests.get(
            f"{NOTIFICATION_SERVICE_URL}/notifications/?user_id={user['id']}",
            timeout=5,
        )
        notifications = response.json() if response.status_code == 200 else []
    except requests.exceptions.RequestException:
        notifications = []
    return render(request, "notifications.html", {"notifications": notifications, "user": user})


def _parse_json_body(request):
    raw_body = request.body or b""
    if not raw_body.strip():
        return {}

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ValueError("Invalid JSON payload")

    if not isinstance(body, dict):
        raise ValueError("Invalid JSON payload")

    return body


def _json_from_upstream(response, service_name):
    try:
        payload = response.json()
    except ValueError:
        status = response.status_code if response.status_code >= 400 else 502
        return {"error": f"{service_name} returned a non-JSON response"}, status

    return payload, response.status_code


@csrf_exempt
def advisor_chat(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, _ = _get_user(request)
    try:
        body = _parse_json_body(request)
    except ValueError:
        return JsonResponse({"error": "Invalid JSON request body"}, status=400)

    payload = {
        "question": body.get("question", ""),
        "user_id": user["id"] if user else None,
    }
    try:
        response = requests.post(f"{ADVISOR_SERVICE_URL}/advisor/chat/", json=payload, timeout=15)
        payload, status = _json_from_upstream(response, "Advisor service")
        return JsonResponse(payload, status=status, safe=isinstance(payload, dict))
    except requests.exceptions.RequestException as exc:
        return JsonResponse({"error": f"Advisor service unavailable: {exc}"}, status=503)


def advisor_profile(request):
    user, _ = _get_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        response = requests.get(f"{ADVISOR_SERVICE_URL}/advisor/profile/{user['id']}/", timeout=10)
        payload, status = _json_from_upstream(response, "Advisor service")
        return JsonResponse(payload, status=status, safe=isinstance(payload, dict))
    except requests.exceptions.RequestException as exc:
        return JsonResponse({"error": f"Advisor service unavailable: {exc}"}, status=503)
