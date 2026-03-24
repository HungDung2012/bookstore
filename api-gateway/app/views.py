import json
import os

import requests
from django.http import JsonResponse
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


def _get_user(request):
    """Helper: láº¥y user info tá»« session token"""
    token = request.session.get("token")
    user = request.session.get("user")
    if token and user:
        return user, token
    return None, None


def health_check(request):
    return JsonResponse({"status": "ok", "service": "api-gateway"})


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ AUTH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@csrf_exempt
def login_view(request):
    if request.method == "POST":
        data = {
            "username": request.POST.get("username"),
            "password": request.POST.get("password"),
        }
        try:
            r = requests.post(f"{USER_SERVICE_URL}/auth/login/", json=data, timeout=5)
            if r.status_code == 200:
                result = r.json()
                request.session["token"] = result["token"]
                request.session["user"] = result["user"]
                return redirect("/books/")
            else:
                error = r.json().get("error", "Login failed")
        except requests.exceptions.RequestException as e:
            error = f"User service unavailable: {e}"
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
            r = requests.post(f"{USER_SERVICE_URL}/auth/register/", json=data, timeout=5)
            if r.status_code == 201:
                result = r.json()
                request.session["token"] = result["token"]
                request.session["user"] = result["user"]
                return redirect("/books/")
            else:
                error = r.json()
        except requests.exceptions.RequestException as e:
            error = f"User service unavailable: {e}"
        return render(request, "register.html", {"error": error})
    return render(request, "register.html")


def logout_view(request):
    request.session.flush()
    return redirect("/login/")


def profile_view(request):
    user, token = _get_user(request)
    if not user:
        return redirect("/login/")
    return render(request, "profile.html", {"user": user})


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ BOOKS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def book_list(request):
    user, _ = _get_user(request)
    try:
        r = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
        r.raise_for_status()
        books = r.json()
        # Get ratings for each book
        for book in books:
            try:
                rating_resp = requests.get(
                    f"{REVIEW_SERVICE_URL}/reviews/rating/{book['id']}/", timeout=3
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
        cat = request.POST.get("category")
        pub = request.POST.get("publisher")
        if cat:
            data["category"] = int(cat)
        if pub:
            data["publisher"] = int(pub)
        try:
            r = requests.post(f"{BOOK_SERVICE_URL}/books/", json=data, timeout=5)
            if r.status_code == 201:
                return redirect("/books/")
            error = r.json()
        except requests.exceptions.RequestException as e:
            error = {"error": str(e)}
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
        }
        cat = request.POST.get("category")
        pub = request.POST.get("publisher")
        data["category"] = int(cat) if cat else None
        data["publisher"] = int(pub) if pub else None
        try:
            r = requests.put(f"{BOOK_SERVICE_URL}/books/{pk}/", json=data, timeout=5)
            if r.status_code == 200:
                return redirect("/books/")
            error = r.json()
        except requests.exceptions.RequestException as e:
            error = {"error": str(e)}
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
        rev_resp = requests.get(f"{REVIEW_SERVICE_URL}/reviews/?book_id={pk}", timeout=5)
        if rev_resp.status_code == 200:
            reviews = rev_resp.json()
        rat_resp = requests.get(f"{REVIEW_SERVICE_URL}/reviews/rating/{pk}/", timeout=3)
        if rat_resp.status_code == 200:
            rating = rat_resp.json()
        # Enrich reviews with usernames
        for rev in reviews:
            try:
                u_resp = requests.get(f"{USER_SERVICE_URL}/users/{rev['user_id']}/", timeout=3)
                if u_resp.status_code == 200:
                    rev["username"] = u_resp.json().get("full_name") or u_resp.json().get(
                        "username"
                    )
            except requests.exceptions.RequestException:
                rev["username"] = f"User #{rev['user_id']}"
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ CART â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
            data = {"cart": user_id, "book_id": int(book_id), "quantity": int(quantity)}
            requests.post(f"{CART_SERVICE_URL}/cart-items/", json=data, timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/cart/{user['id']}/")


def view_cart(request, customer_id):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        r = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
        r.raise_for_status()
        items = r.json()
        try:
            book_resp = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            if book_resp.status_code == 200:
                books = {b["id"]: b for b in book_resp.json()}
                for item in items:
                    book_id = item.get("book_id")
                    if book_id and book_id in books:
                        item["book_title"] = books[book_id].get("title")
                        item["book_price"] = books[book_id].get("price")
        except requests.exceptions.RequestException:
            pass
    except requests.exceptions.RequestException:
        items = []
    return render(request, "cart.html", {"items": items, "customer_id": customer_id, "user": user})


@csrf_exempt
def update_cart_item(request, customer_id):
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
    return redirect(f"/cart/{customer_id}/")


@csrf_exempt
def delete_cart_item(request, customer_id, item_id):
    if request.method == "POST":
        try:
            requests.delete(f"{CART_SERVICE_URL}/carts/{customer_id}/delete-item/{item_id}/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/cart/{customer_id}/")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ ORDERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@csrf_exempt
def checkout(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if request.method == "POST":
        data = {
            "user_id": user["id"],
            "shipping_name": request.POST.get("shipping_name"),
            "shipping_phone": request.POST.get("shipping_phone"),
            "shipping_address": request.POST.get("shipping_address"),
            "note": request.POST.get("note", ""),
            "payment_method": request.POST.get("payment_method", "cod"),
        }
        try:
            r = requests.post(f"{ORDER_SERVICE_URL}/orders/checkout/", json=data, timeout=10)
            if r.status_code == 201:
                order = r.json()
                # Send notification
                try:
                    requests.post(
                        f"{NOTIFICATION_SERVICE_URL}/notifications/",
                        json={
                            "user_id": user["id"],
                            "type": "order_confirmed",
                            "title": f"Order #{order['id']} placed!",
                            "message": f"Your order of ${order['total_amount']} has been placed successfully.",
                            "reference_id": order["id"],
                        },
                        timeout=3,
                    )
                except requests.exceptions.RequestException:
                    pass
                return redirect(f"/orders/{order['id']}/")
            else:
                error = r.json().get("error", "Checkout failed")
                return render(request, "checkout.html", {"error": error, "user": user})
        except requests.exceptions.RequestException as e:
            return render(request, "checkout.html", {"error": str(e), "user": user})
    # GET: show checkout form
    return render(request, "checkout.html", {"user": user})


def order_list(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        r = requests.get(f"{ORDER_SERVICE_URL}/orders/?user_id={user['id']}", timeout=5)
        orders = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        orders = []
    return render(request, "orders.html", {"orders": orders, "user": user})


def order_detail(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        r = requests.get(f"{ORDER_SERVICE_URL}/orders/{pk}/", timeout=5)
        order = r.json() if r.status_code == 200 else {}
    except requests.exceptions.RequestException:
        order = {}
    return render(request, "order_detail.html", {"order": order, "user": user})


@csrf_exempt
def cancel_order(request, pk):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    if request.method == "POST":
        try:
            requests.post(f"{ORDER_SERVICE_URL}/orders/{pk}/cancel/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect(f"/orders/{pk}/")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ NOTIFICATIONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def notifications_view(request):
    user, _ = _get_user(request)
    if not user:
        return redirect("/login/")
    try:
        r = requests.get(f"{NOTIFICATION_SERVICE_URL}/notifications/?user_id={user['id']}", timeout=5)
        notifs = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        notifs = []
    return render(request, "notifications.html", {"notifications": notifs, "user": user})
