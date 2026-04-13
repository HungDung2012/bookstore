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
