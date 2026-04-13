import os

import requests


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


BOOK_SERVICE_URL = _service_url("BOOK_SERVICE_URL", "book-service:8000")
ORDER_SERVICE_URL = _service_url("ORDER_SERVICE_URL", "order-service:8000")
REVIEW_SERVICE_URL = _service_url("REVIEW_SERVICE_URL", "review-service:8000")
CART_SERVICE_URL = _service_url("CART_SERVICE_URL", "cart-service:8000")
USER_SERVICE_URL = _service_url("USER_SERVICE_URL", "user-service:8000")


class UpstreamClient:
    def __init__(self, timeout=5):
        self.timeout = timeout

    def _get(self, url):
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_books(self):
        return self._get(f"{BOOK_SERVICE_URL}/books/")

    def get_orders(self, user_id):
        return self._get(f"{ORDER_SERVICE_URL}/orders/?user_id={user_id}")

    def get_reviews(self, user_id):
        return self._get(f"{REVIEW_SERVICE_URL}/reviews/?user_id={user_id}")

    def get_cart(self, user_id):
        return self._get(f"{CART_SERVICE_URL}/carts/{user_id}/")

    def get_user(self, user_id):
        return self._get(f"{USER_SERVICE_URL}/users/{user_id}/")
