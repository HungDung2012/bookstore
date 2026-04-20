# Bookstore AI Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and integrate an `advisor-service` that classifies customer behavior with a deep learning model, retrieves knowledge-base context, generates grounded chat responses, and exposes a popup advisor widget in the existing bookstore frontend.

**Architecture:** Add a new Django-based microservice following the existing repository pattern. The service aggregates behavior data from current microservices, runs `model_behavior` inference, retrieves KB documents and relevant books, calls an external LLM API for grounded responses, and is consumed by `api-gateway` through JSON endpoints and a popup chat widget.

**Tech Stack:** Django, Django REST Framework, requests, numpy, pandas, scikit-learn, tensorflow-cpu, sentence-transformers or a lightweight embedding fallback, FAISS or cosine similarity fallback, existing Docker and Render deployment files.

---

## File Structure

### New `advisor-service` files

- Create: `advisor-service/manage.py`
- Create: `advisor-service/Dockerfile`
- Create: `advisor-service/requirements.txt`
- Create: `advisor-service/seed_data.py`
- Create: `advisor-service/advisor_service/__init__.py`
- Create: `advisor-service/advisor_service/asgi.py`
- Create: `advisor-service/advisor_service/settings.py`
- Create: `advisor-service/advisor_service/urls.py`
- Create: `advisor-service/advisor_service/wsgi.py`
- Create: `advisor-service/app/__init__.py`
- Create: `advisor-service/app/admin.py`
- Create: `advisor-service/app/apps.py`
- Create: `advisor-service/app/models.py`
- Create: `advisor-service/app/serializers.py`
- Create: `advisor-service/app/views.py`
- Create: `advisor-service/app/tests.py`
- Create: `advisor-service/app/services/__init__.py`
- Create: `advisor-service/app/services/clients.py`
- Create: `advisor-service/app/services/features.py`
- Create: `advisor-service/app/services/behavior_model.py`
- Create: `advisor-service/app/services/knowledge_base.py`
- Create: `advisor-service/app/services/retriever.py`
- Create: `advisor-service/app/services/prompting.py`
- Create: `advisor-service/app/services/advisor.py`
- Create: `advisor-service/app/migrations/__init__.py`
- Create: `advisor-service/app/management/__init__.py`
- Create: `advisor-service/app/management/commands/__init__.py`
- Create: `advisor-service/app/management/commands/prepare_behavior_data.py`
- Create: `advisor-service/app/management/commands/train_behavior_model.py`
- Create: `advisor-service/app/data/knowledge_base/faqs.json`
- Create: `advisor-service/app/data/knowledge_base/policies.json`
- Create: `advisor-service/app/data/knowledge_base/categories.json`
- Create: `advisor-service/app/data/knowledge_base/segment_advice.json`
- Create: `advisor-service/app/data/training/.gitkeep`
- Create: `advisor-service/app/data/models/.gitkeep`
- Create: `advisor-service/app/data/index/.gitkeep`

### Existing files to modify

- Modify: `docker-compose.yml`
- Modify: `render.yaml`
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/app/tests.py`
- Modify: `api-gateway/app/templates/base.html`
- Modify: `api-gateway/api_gateway/urls.py`

### Optional docs to update after implementation

- Modify: `DEPLOY_RENDER.md`

---

### Task 1: Scaffold the New Advisor Service

**Files:**
- Create: `advisor-service/manage.py`
- Create: `advisor-service/Dockerfile`
- Create: `advisor-service/requirements.txt`
- Create: `advisor-service/seed_data.py`
- Create: `advisor-service/advisor_service/__init__.py`
- Create: `advisor-service/advisor_service/asgi.py`
- Create: `advisor-service/advisor_service/settings.py`
- Create: `advisor-service/advisor_service/urls.py`
- Create: `advisor-service/advisor_service/wsgi.py`
- Create: `advisor-service/app/__init__.py`
- Create: `advisor-service/app/admin.py`
- Create: `advisor-service/app/apps.py`
- Create: `advisor-service/app/models.py`
- Create: `advisor-service/app/serializers.py`
- Create: `advisor-service/app/views.py`
- Create: `advisor-service/app/tests.py`
- Create: `advisor-service/app/migrations/__init__.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing health-check and chat smoke tests**

```python
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient


class AdvisorApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_endpoint_returns_service_name(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "advisor-service")

    @patch("app.services.advisor.AdvisorService.chat")
    def test_chat_endpoint_returns_service_payload(self, chat_mock):
        chat_mock.return_value = {
            "answer": "Try technical books.",
            "behavior_segment": "tech_reader",
            "recommended_books": [],
            "sources": [],
        }

        response = self.client.post(
            "/advisor/chat/",
            {"user_id": 1, "question": "Recommend books"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "tech_reader")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests.AdvisorApiTests -v 2`
Expected: FAIL because the service files and URLs do not exist yet.

- [ ] **Step 3: Add the minimal Django service skeleton**

```python
# advisor-service/app/views.py
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AdvisorChatSerializer
from .services.advisor import AdvisorService


def health_check(request):
    return JsonResponse({"status": "ok", "service": "advisor-service"})


class AdvisorChatView(APIView):
    def post(self, request):
        serializer = AdvisorChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = AdvisorService().chat(**serializer.validated_data)
        return Response(payload, status=status.HTTP_200_OK)
```

```python
# advisor-service/app/serializers.py
from rest_framework import serializers


class AdvisorChatSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False, allow_null=True)
    question = serializers.CharField()
```

```python
# advisor-service/app/services/advisor.py
class AdvisorService:
    def chat(self, user_id=None, question=""):
        return {
            "answer": "Advisor service is ready.",
            "behavior_segment": "casual_buyer",
            "recommended_books": [],
            "sources": [],
        }
```

```python
# advisor-service/advisor_service/urls.py
from django.contrib import admin
from django.urls import path

from app.views import AdvisorChatView, health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check),
    path("advisor/chat/", AdvisorChatView.as_view()),
]
```

- [ ] **Step 4: Add minimal settings, requirements, and Docker startup**

```text
# advisor-service/requirements.txt
django
djangorestframework
requests
dj-database-url
gunicorn
numpy
pandas
scikit-learn
tensorflow-cpu
sentence-transformers
faiss-cpu
```

```dockerfile
# advisor-service/Dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/

CMD ["sh", "-c", "python manage.py migrate && exec gunicorn advisor_service.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests.AdvisorApiTests -v 2`
Expected: PASS with 2 tests.

- [ ] **Step 6: Commit**

```bash
git add advisor-service
git commit -m "feat: scaffold advisor service"
```

### Task 2: Build Service Clients and Behavior Feature Extraction

**Files:**
- Create: `advisor-service/app/services/clients.py`
- Create: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing feature extraction tests**

```python
from app.services.features import build_behavior_features


def test_build_behavior_features_aggregates_orders_reviews_and_cart():
    profile = {"id": 7, "full_name": "Alice"}
    books = [
        {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
        {"id": 2, "title": "Poems", "price": "10.00", "category": 5, "publisher": 2},
    ]
    orders = [
        {
            "id": 1,
            "total_amount": "40.00",
            "items": [
                {"book_id": 1, "quantity": 2, "unit_price": "20.00"},
            ],
        }
    ]
    reviews = [{"book_id": 1, "rating": 5}, {"book_id": 2, "rating": 3}]
    cart_items = [{"book_id": 2, "quantity": 1}]

    result = build_behavior_features(profile, books, orders, reviews, cart_items)

    assert result["order_count"] == 1
    assert result["total_spent"] == 40.0
    assert result["review_count"] == 2
    assert result["cart_item_count"] == 1
    assert result["category_3_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL with import or key errors because the feature builder does not exist.

- [ ] **Step 3: Implement client wrappers for upstream services**

```python
# advisor-service/app/services/clients.py
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
```

```python
# advisor-service/app/services/features.py
from collections import Counter


def build_behavior_features(profile, books, orders, reviews, cart_items):
    book_by_id = {book["id"]: book for book in books}
    category_counter = Counter()
    publisher_counter = Counter()
    total_spent = 0.0
    total_quantity = 0

    for order in orders:
        total_spent += float(order.get("total_amount", 0) or 0)
        for item in order.get("items", []):
            quantity = int(item.get("quantity", 0) or 0)
            total_quantity += quantity
            book = book_by_id.get(item["book_id"], {})
            if book.get("category"):
                category_counter[book["category"]] += quantity
            if book.get("publisher"):
                publisher_counter[book["publisher"]] += quantity

    review_ratings = [int(review.get("rating", 0) or 0) for review in reviews]
    avg_rating = sum(review_ratings) / len(review_ratings) if review_ratings else 0.0

    features = {
        "user_id": profile.get("id"),
        "order_count": len(orders),
        "total_spent": round(total_spent, 2),
        "average_order_value": round(total_spent / len(orders), 2) if orders else 0.0,
        "total_quantity": total_quantity,
        "review_count": len(reviews),
        "average_review_rating": round(avg_rating, 2),
        "cart_item_count": len(cart_items),
        "premium_interest_score": 1.0 if orders and (total_spent / max(total_quantity, 1)) >= 18 else 0.0,
        "budget_interest_score": 1.0 if total_quantity and (total_spent / total_quantity) < 12 else 0.0,
    }

    for category_id, count in category_counter.items():
        features[f"category_{category_id}_count"] = count
    for publisher_id, count in publisher_counter.items():
        features[f"publisher_{publisher_id}_count"] = count

    return features
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for the feature extraction test and the earlier smoke tests.

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/tests.py advisor-service/app/services/clients.py advisor-service/app/services/features.py
git commit -m "feat: add advisor feature engineering"
```

### Task 3: Add Training Data Preparation and Segment Labeling

**Files:**
- Create: `advisor-service/app/management/commands/prepare_behavior_data.py`
- Modify: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/tests.py`
- Create: `advisor-service/app/data/training/.gitkeep`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing pseudo-labeling test**

```python
from app.services.features import infer_behavior_label


def test_infer_behavior_label_prefers_tech_reader_when_technical_category_dominates():
    features = {
        "order_count": 4,
        "total_spent": 120.0,
        "category_3_count": 8,
        "category_5_count": 1,
        "budget_interest_score": 0.0,
    }

    assert infer_behavior_label(features) == "tech_reader"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL because `infer_behavior_label` does not exist.

- [ ] **Step 3: Add deterministic labeling rules used for demo training**

```python
# advisor-service/app/services/features.py
def infer_behavior_label(features):
    if features.get("budget_interest_score", 0) >= 1 and features.get("order_count", 0) >= 2:
        return "bargain_hunter"
    if features.get("category_3_count", 0) >= max(features.get("category_5_count", 0), 1) * 2:
        return "tech_reader"
    if features.get("category_5_count", 0) >= max(features.get("category_3_count", 0), 1) * 2:
        return "literature_reader"
    if features.get("category_8_count", 0) >= 2:
        return "family_reader"
    return "casual_buyer"
```

- [ ] **Step 4: Add the management command that exports training rows**

```python
# advisor-service/app/management/commands/prepare_behavior_data.py
import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from app.services.clients import UpstreamClient
from app.services.features import build_behavior_features, infer_behavior_label


class Command(BaseCommand):
    help = "Prepare behavior training data from upstream microservices."

    def handle(self, *args, **options):
        client = UpstreamClient()
        books = client.get_books()
        output_path = Path("app/data/training/behavior_dataset.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for user_id in range(1, 21):
            try:
                profile = client.get_user(user_id)
                orders = client.get_orders(user_id)
                reviews = client.get_reviews(user_id)
                cart_items = client.get_cart(user_id)
            except Exception:
                continue

            features = build_behavior_features(profile, books, orders, reviews, cart_items)
            features["label"] = infer_behavior_label(features)
            rows.append(features)

        if not rows:
            self.stdout.write(self.style.WARNING("No rows generated"))
            return

        fieldnames = sorted({key for row in rows for key in row.keys()})
        with output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} rows to {output_path}"))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for labeling tests and existing service tests.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/services/features.py advisor-service/app/management/commands/prepare_behavior_data.py advisor-service/app/tests.py advisor-service/app/data/training/.gitkeep
git commit -m "feat: add behavior dataset preparation"
```

### Task 4: Train and Load the Deep Learning `model_behavior`

**Files:**
- Create: `advisor-service/app/management/commands/train_behavior_model.py`
- Create: `advisor-service/app/services/behavior_model.py`
- Modify: `advisor-service/app/tests.py`
- Create: `advisor-service/app/data/models/.gitkeep`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing model wrapper test**

```python
from unittest.mock import patch

from app.services.behavior_model import BehaviorModelService


@patch("app.services.behavior_model.load_model")
def test_behavior_model_predict_returns_known_label(load_model_mock):
    fake_model = load_model_mock.return_value
    fake_model.predict.return_value = [[0.8, 0.1, 0.05, 0.03, 0.02]]

    service = BehaviorModelService()
    result = service.predict(
        {
            "order_count": 4,
            "total_spent": 100.0,
            "category_3_count": 9,
        }
    )

    assert result["behavior_segment"] == "tech_reader"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL because the model service does not exist.

- [ ] **Step 3: Add the train command**

```python
# advisor-service/app/management/commands/train_behavior_model.py
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Dropout
from tensorflow.keras.utils import to_categorical


class Command(BaseCommand):
    help = "Train the deep learning behavior classifier."

    def handle(self, *args, **options):
        dataset_path = Path("app/data/training/behavior_dataset.csv")
        df = pd.read_csv(dataset_path).fillna(0)

        y = df.pop("label")
        if "user_id" in df.columns:
            df.pop("user_id")

        encoder = LabelEncoder()
        y_encoded = encoder.fit_transform(y)
        y_one_hot = to_categorical(y_encoded)

        X_train, X_test, y_train, y_test = train_test_split(
            df.values, y_one_hot, test_size=0.2, random_state=42
        )

        model = Sequential(
            [
                Dense(32, activation="relu", input_shape=(X_train.shape[1],)),
                Dropout(0.2),
                Dense(16, activation="relu"),
                Dense(y_one_hot.shape[1], activation="softmax"),
            ]
        )
        model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
        model.fit(X_train, y_train, epochs=20, batch_size=8, verbose=0)

        output_dir = Path("app/data/models")
        output_dir.mkdir(parents=True, exist_ok=True)
        model.save(output_dir / "model_behavior.h5")
        (output_dir / "labels.txt").write_text("\n".join(encoder.classes_), encoding="utf-8")
        (output_dir / "features.txt").write_text("\n".join(df.columns.tolist()), encoding="utf-8")
        _, accuracy = model.evaluate(X_test, y_test, verbose=0)
        self.stdout.write(self.style.SUCCESS(f"Model trained with accuracy={accuracy:.2f}"))
```

- [ ] **Step 4: Add the inference wrapper**

```python
# advisor-service/app/services/behavior_model.py
from pathlib import Path

import numpy as np
from tensorflow.keras.models import load_model


class BehaviorModelService:
    labels = ["tech_reader", "literature_reader", "family_reader", "bargain_hunter", "casual_buyer"]

    def __init__(self, model_path="app/data/models/model_behavior.h5", features_path="app/data/models/features.txt"):
        self.model_path = Path(model_path)
        self.features_path = Path(features_path)
        self._model = None

    def _load_model(self):
        if self._model is None and self.model_path.exists():
            self._model = load_model(self.model_path)
        return self._model

    def _vectorize(self, features):
        feature_names = self.features_path.read_text(encoding="utf-8").splitlines()
        return np.array([[float(features.get(name, 0.0)) for name in feature_names]])

    def predict(self, features):
        model = self._load_model()
        if model is None:
            return {"behavior_segment": "casual_buyer", "probabilities": {}}

        probabilities = model.predict(self._vectorize(features), verbose=0)[0]
        best_index = int(np.argmax(probabilities))
        return {
            "behavior_segment": self.labels[best_index],
            "probabilities": {
                label: float(prob)
                for label, prob in zip(self.labels, probabilities)
            },
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for the model service test and the earlier tests.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/management/commands/train_behavior_model.py advisor-service/app/services/behavior_model.py advisor-service/app/tests.py advisor-service/app/data/models/.gitkeep
git commit -m "feat: add deep learning behavior model"
```

### Task 5: Add the Knowledge Base Loader and Retriever

**Files:**
- Create: `advisor-service/app/data/knowledge_base/faqs.json`
- Create: `advisor-service/app/data/knowledge_base/policies.json`
- Create: `advisor-service/app/data/knowledge_base/categories.json`
- Create: `advisor-service/app/data/knowledge_base/segment_advice.json`
- Create: `advisor-service/app/services/knowledge_base.py`
- Create: `advisor-service/app/services/retriever.py`
- Modify: `advisor-service/app/tests.py`
- Create: `advisor-service/app/data/index/.gitkeep`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing KB retrieval test**

```python
from app.services.knowledge_base import KnowledgeBaseService
from app.services.retriever import RetrieverService


def test_retriever_returns_shipping_document_for_shipping_question():
    kb = KnowledgeBaseService("app/data/knowledge_base")
    retriever = RetrieverService(kb)

    docs = retriever.search("What is your shipping policy?", target_segment="casual_buyer", top_k=2)

    assert docs
    assert "shipping" in docs[0]["text"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL because the KB files and retriever do not exist.

- [ ] **Step 3: Add KB source documents**

```json
[
  {
    "id": "faq_shipping_policy",
    "title": "Shipping policy",
    "doc_type": "faq",
    "source_service": "notification-service",
    "category": "operations",
    "target_segment": "all",
    "tags": ["shipping", "delivery", "policy"],
    "text": "Orders are processed after successful confirmation. Shipping updates are sent through the notification system."
  }
]
```

```json
[
  {
    "id": "segment_tech_reader",
    "title": "Advice for technology readers",
    "doc_type": "segment_advice",
    "source_service": "advisor-service",
    "category": "behavior",
    "target_segment": "tech_reader",
    "tags": ["technology", "programming", "career"],
    "text": "Technology-oriented customers usually prefer programming, software engineering, data, and innovation books."
  }
]
```

- [ ] **Step 4: Implement KB loading and a lightweight retriever**

```python
# advisor-service/app/services/knowledge_base.py
import json
from pathlib import Path


class KnowledgeBaseService:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def load_documents(self):
        documents = []
        for path in sorted(self.base_path.glob("*.json")):
            documents.extend(json.loads(path.read_text(encoding="utf-8")))
        return documents
```

```python
# advisor-service/app/services/retriever.py
from collections import Counter


class RetrieverService:
    def __init__(self, kb_service):
        self.kb_service = kb_service
        self.documents = kb_service.load_documents()

    def _score(self, query, document, target_segment=None):
        query_terms = Counter(query.lower().split())
        text = f"{document.get('title', '')} {document.get('text', '')} {' '.join(document.get('tags', []))}".lower()
        score = sum(text.count(term) for term in query_terms)
        if target_segment and document.get("target_segment") in (target_segment, "all"):
            score += 2
        return score

    def search(self, query, target_segment=None, top_k=3):
        ranked = sorted(
            self.documents,
            key=lambda doc: self._score(query, doc, target_segment=target_segment),
            reverse=True,
        )
        return [doc for doc in ranked if self._score(query, doc, target_segment=target_segment) > 0][:top_k]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for KB retrieval and all prior tests.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/data/knowledge_base advisor-service/app/services/knowledge_base.py advisor-service/app/services/retriever.py advisor-service/app/tests.py advisor-service/app/data/index/.gitkeep
git commit -m "feat: add advisor knowledge base retrieval"
```

### Task 6: Implement Prompting, LLM Fallback, and the Advisor Orchestrator

**Files:**
- Create: `advisor-service/app/services/prompting.py`
- Modify: `advisor-service/app/services/advisor.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing advisor orchestration test**

```python
from unittest.mock import patch

from app.services.advisor import AdvisorService


@patch("app.services.advisor.UpstreamClient")
@patch("app.services.advisor.BehaviorModelService")
@patch("app.services.advisor.RetrieverService")
def test_advisor_service_combines_behavior_and_sources(retriever_cls, model_cls, client_cls):
    client = client_cls.return_value
    client.get_books.return_value = [{"id": 1, "title": "Python 101", "category": 3, "publisher": 2, "price": "20.00"}]
    client.get_orders.return_value = []
    client.get_reviews.return_value = []
    client.get_cart.return_value = []
    client.get_user.return_value = {"id": 1, "full_name": "Alice"}

    model_cls.return_value.predict.return_value = {"behavior_segment": "tech_reader", "probabilities": {"tech_reader": 0.9}}
    retriever_cls.return_value.search.return_value = [{"id": "segment_tech_reader", "text": "Technology readers prefer programming books."}]

    result = AdvisorService().chat(user_id=1, question="Recommend books")

    assert result["behavior_segment"] == "tech_reader"
    assert result["sources"][0]["id"] == "segment_tech_reader"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL because the advisor service does not orchestrate model, retriever, and answer generation yet.

- [ ] **Step 3: Add prompt building and a deterministic fallback answer**

```python
# advisor-service/app/services/prompting.py
def build_chat_prompt(question, behavior_segment, feature_summary, documents, recommended_books):
    kb_text = "\n".join(f"- {doc['title']}: {doc['text']}" for doc in documents)
    books_text = "\n".join(f"- {book['title']} (${book['price']})" for book in recommended_books)
    return f"""
You are an AI bookstore advisor.
User question: {question}
Behavior segment: {behavior_segment}
Behavior explanation: {feature_summary}
Knowledge base:
{kb_text}
Suggested books:
{books_text}
Answer in a concise and grounded way. Explain why the recommendations match the user's behavior.
""".strip()


def build_fallback_answer(question, behavior_segment, recommended_books):
    book_names = ", ".join(book["title"] for book in recommended_books[:3]) or "our featured catalog"
    return (
        f"Based on your behavior segment `{behavior_segment}`, I recommend starting with {book_names}. "
        f"This matches your recent shopping pattern. For service questions, I will answer using the bookstore knowledge base."
    )
```

- [ ] **Step 4: Expand the advisor orchestrator**

```python
# advisor-service/app/services/advisor.py
import os

import requests

from .behavior_model import BehaviorModelService
from .clients import UpstreamClient
from .features import build_behavior_features
from .knowledge_base import KnowledgeBaseService
from .prompting import build_chat_prompt, build_fallback_answer
from .retriever import RetrieverService


class AdvisorService:
    def __init__(self):
        self.client = UpstreamClient()
        self.model_service = BehaviorModelService()
        self.retriever = RetrieverService(KnowledgeBaseService("app/data/knowledge_base"))

    def _pick_books(self, books, segment, limit=3):
        if segment == "tech_reader":
            filtered = [book for book in books if book.get("category") == 3]
        elif segment == "literature_reader":
            filtered = [book for book in books if book.get("category") == 5]
        else:
            filtered = books
        return filtered[:limit]

    def _call_llm(self, prompt):
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if not api_key:
            return None
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def chat(self, user_id=None, question=""):
        books = self.client.get_books()
        profile = {"id": user_id} if not user_id else self.client.get_user(user_id)
        orders = self.client.get_orders(user_id) if user_id else []
        reviews = self.client.get_reviews(user_id) if user_id else []
        cart_items = self.client.get_cart(user_id) if user_id else []

        features = build_behavior_features(profile, books, orders, reviews, cart_items)
        prediction = self.model_service.predict(features)
        behavior_segment = prediction["behavior_segment"]
        recommended_books = self._pick_books(books, behavior_segment)
        sources = self.retriever.search(question, target_segment=behavior_segment, top_k=3)
        feature_summary = f"Predicted segment is {behavior_segment} from orders={features['order_count']}, reviews={features['review_count']}."
        prompt = build_chat_prompt(question, behavior_segment, feature_summary, sources, recommended_books)

        try:
            answer = self._call_llm(prompt) or build_fallback_answer(question, behavior_segment, recommended_books)
        except Exception:
            answer = build_fallback_answer(question, behavior_segment, recommended_books)

        return {
            "answer": answer,
            "behavior_segment": behavior_segment,
            "recommended_books": recommended_books,
            "sources": sources,
            "feature_summary": feature_summary,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for orchestration and all existing tests.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/services/prompting.py advisor-service/app/services/advisor.py advisor-service/app/tests.py
git commit -m "feat: implement advisor orchestration"
```

### Task 7: Expose the Behavior Profile Endpoint

**Files:**
- Modify: `advisor-service/app/serializers.py`
- Modify: `advisor-service/app/views.py`
- Modify: `advisor-service/advisor_service/urls.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing profile endpoint test**

```python
from unittest.mock import patch


@patch("app.services.advisor.AdvisorService.profile")
def test_profile_endpoint_returns_behavior_segment(profile_mock):
    profile_mock.return_value = {
        "behavior_segment": "literature_reader",
        "feature_summary": "Frequent purchases in literature.",
    }

    response = self.client.get("/advisor/profile/4/")

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["behavior_segment"], "literature_reader")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: FAIL because the endpoint does not exist.

- [ ] **Step 3: Add the endpoint and profile service method**

```python
# advisor-service/app/views.py
class AdvisorProfileView(APIView):
    def get(self, request, user_id):
        payload = AdvisorService().profile(user_id=user_id)
        return Response(payload, status=status.HTTP_200_OK)
```

```python
# advisor-service/app/services/advisor.py
    def profile(self, user_id):
        books = self.client.get_books()
        profile = self.client.get_user(user_id)
        orders = self.client.get_orders(user_id)
        reviews = self.client.get_reviews(user_id)
        cart_items = self.client.get_cart(user_id)
        features = build_behavior_features(profile, books, orders, reviews, cart_items)
        prediction = self.model_service.predict(features)
        prediction["feature_summary"] = (
            f"Predicted segment is {prediction['behavior_segment']} from "
            f"{features['order_count']} orders and {features['review_count']} reviews."
        )
        return prediction
```

```python
# advisor-service/advisor_service/urls.py
urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check),
    path("advisor/chat/", AdvisorChatView.as_view()),
    path("advisor/profile/<int:user_id>/", AdvisorProfileView.as_view()),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS for the new profile endpoint and existing tests.

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/serializers.py advisor-service/app/views.py advisor-service/advisor_service/urls.py advisor-service/app/tests.py
git commit -m "feat: add advisor behavior profile endpoint"
```

### Task 8: Integrate Advisor Endpoints into `api-gateway`

**Files:**
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/api_gateway/urls.py`
- Modify: `api-gateway/app/tests.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing gateway proxy tests**

```python
from unittest.mock import Mock, patch


@patch("app.views.requests.post")
def test_advisor_chat_proxy_returns_json(post_mock):
    gateway_response = Mock(status_code=200)
    gateway_response.json.return_value = {
        "answer": "Read more programming books.",
        "behavior_segment": "tech_reader",
        "recommended_books": [],
        "sources": [],
    }
    post_mock.return_value = gateway_response

    response = self.client.post(
        "/advisor/chat/",
        {"question": "Recommend books"},
        content_type="application/json",
    )

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["behavior_segment"], "tech_reader")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api-gateway; python manage.py test app.tests -v 2`
Expected: FAIL because no advisor proxy route exists.

- [ ] **Step 3: Add gateway advisor proxy views**

```python
# api-gateway/app/views.py
ADVISOR_SERVICE_URL = _service_url("ADVISOR_SERVICE_URL", "advisor-service:8000")


@csrf_exempt
def advisor_chat(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, _ = _get_user(request)
    body = json.loads(request.body or "{}")
    payload = {
        "question": body.get("question", ""),
        "user_id": user["id"] if user else None,
    }
    try:
        response = requests.post(f"{ADVISOR_SERVICE_URL}/advisor/chat/", json=payload, timeout=15)
        return JsonResponse(response.json(), status=response.status_code)
    except requests.exceptions.RequestException as exc:
        return JsonResponse({"error": f"Advisor service unavailable: {exc}"}, status=503)


def advisor_profile(request):
    user, _ = _get_user(request)
    if not user:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        response = requests.get(f"{ADVISOR_SERVICE_URL}/advisor/profile/{user['id']}/", timeout=10)
        return JsonResponse(response.json(), status=response.status_code)
    except requests.exceptions.RequestException as exc:
        return JsonResponse({"error": f"Advisor service unavailable: {exc}"}, status=503)
```

```python
# api-gateway/api_gateway/urls.py
path("advisor/chat/", advisor_chat, name="advisor_chat"),
path("advisor/profile/", advisor_profile, name="advisor_profile"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api-gateway; python manage.py test app.tests -v 2`
Expected: PASS for the new proxy tests and the existing auth tests.

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/views.py api-gateway/api_gateway/urls.py api-gateway/app/tests.py
git commit -m "feat: proxy advisor service through gateway"
```

### Task 9: Add the Popup Chat Widget to the Frontend

**Files:**
- Modify: `api-gateway/app/templates/base.html`
- Modify: `api-gateway/app/tests.py`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing template test**

```python
def test_books_page_contains_ai_advisor_launcher(self):
    response = self.client.get("/books/")
    self.assertContains(response, "AI Book Advisor")
    self.assertContains(response, "advisor-chat-launcher")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api-gateway; python manage.py test app.tests -v 2`
Expected: FAIL because the base template does not render the chat widget.

- [ ] **Step 3: Add the popup widget markup, styles, and fetch logic**

```html
<!-- api-gateway/app/templates/base.html -->
<button id="advisor-chat-launcher" class="advisor-chat-launcher" type="button">
  <i class="fa-solid fa-robot"></i>
  <span>AI Book Advisor</span>
</button>

<section id="advisor-chat-panel" class="advisor-chat-panel" hidden>
  <div class="advisor-chat-header">
    <div>
      <strong>AI Book Advisor</strong>
      <p>Personalized book and service consultation</p>
    </div>
    <button id="advisor-chat-close" type="button"><i class="fa-solid fa-xmark"></i></button>
  </div>
  <div class="advisor-chat-suggestions">
    <button type="button" data-question="Recommend books for me">Recommend books for me</button>
    <button type="button" data-question="What type of books should I read?">What type of books should I read?</button>
    <button type="button" data-question="What is your shipping policy?">What is your shipping policy?</button>
  </div>
  <div id="advisor-chat-messages" class="advisor-chat-messages"></div>
  <form id="advisor-chat-form" class="advisor-chat-form">
    <input id="advisor-chat-input" type="text" placeholder="Ask for book or service advice">
    <button type="submit">Send</button>
  </form>
</section>
```

```html
<script>
  const launcher = document.getElementById("advisor-chat-launcher");
  const panel = document.getElementById("advisor-chat-panel");
  const closeButton = document.getElementById("advisor-chat-close");
  const form = document.getElementById("advisor-chat-form");
  const input = document.getElementById("advisor-chat-input");
  const messages = document.getElementById("advisor-chat-messages");

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = `advisor-message advisor-message-${role}`;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  launcher?.addEventListener("click", () => panel.hidden = false);
  closeButton?.addEventListener("click", () => panel.hidden = true);

  document.querySelectorAll(".advisor-chat-suggestions button").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.question;
      form.requestSubmit();
    });
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;

    appendMessage("user", question);
    appendMessage("assistant", "Thinking...");
    input.value = "";

    const response = await fetch("/advisor/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await response.json();
    messages.lastChild.remove();
    appendMessage("assistant", data.answer || data.error || "Advisor unavailable.");
  });
</script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api-gateway; python manage.py test app.tests -v 2`
Expected: PASS for the template test and existing gateway tests.

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/templates/base.html api-gateway/app/tests.py
git commit -m "feat: add popup AI advisor widget"
```

### Task 10: Wire Deployment and Local Runtime Configuration

**Files:**
- Modify: `docker-compose.yml`
- Modify: `render.yaml`
- Modify: `DEPLOY_RENDER.md`
- Test: `docker-compose.yml`
- Test: `render.yaml`

- [ ] **Step 1: Write the failing config review checklist**

```text
docker-compose must include advisor-service
api-gateway must receive ADVISOR_SERVICE_URL
advisor-service must receive BOOK_SERVICE_URL, ORDER_SERVICE_URL, REVIEW_SERVICE_URL, CART_SERVICE_URL, USER_SERVICE_URL
render.yaml must declare bookstore-advisor-service
render.yaml must expose ADVISOR_SERVICE_URL to bookstore-api-gateway
```

- [ ] **Step 2: Run config verification before editing**

Run: `rg -n "advisor-service|ADVISOR_SERVICE_URL" docker-compose.yml render.yaml DEPLOY_RENDER.md`
Expected: no matches before implementation.

- [ ] **Step 3: Update Docker Compose and Render**

```yaml
# docker-compose.yml
  api-gateway:
    depends_on:
      - advisor-service
    environment:
      ADVISOR_SERVICE_URL: http://advisor-service:8000

  advisor-service:
    build: ./advisor-service
    ports:
      - "8009:8000"
    environment:
      BOOK_SERVICE_URL: http://book-service:8000
      ORDER_SERVICE_URL: http://order-service:8000
      REVIEW_SERVICE_URL: http://review-service:8000
      CART_SERVICE_URL: http://cart-service:8000
      USER_SERVICE_URL: http://user-service:8000
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_MODEL: ${OPENAI_MODEL:-gpt-4o-mini}
```

```yaml
# render.yaml
  - type: web
    name: bookstore-api-gateway
    envVars:
      - key: ADVISOR_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-advisor-service
          property: hostport

  - type: pserv
    name: bookstore-advisor-service
    runtime: docker
    plan: starter
    region: singapore
    dockerContext: ./advisor-service
    dockerfilePath: ./advisor-service/Dockerfile
    disk:
      name: advisor-data
      mountPath: /var/data
      sizeGB: 1
    envVars:
      - key: PORT
        value: "8000"
      - key: DEBUG
        value: "false"
      - key: ALLOWED_HOSTS
        value: "*"
      - key: SECRET_KEY
        generateValue: true
      - key: BOOK_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-book-service
          property: hostport
      - key: ORDER_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-order-service
          property: hostport
      - key: REVIEW_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-review-service
          property: hostport
      - key: CART_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-cart-service
          property: hostport
      - key: USER_SERVICE_URL
        fromService:
          type: pserv
          name: bookstore-user-service
          property: hostport
      - key: OPENAI_API_KEY
        sync: false
      - key: OPENAI_MODEL
        value: "gpt-4o-mini"
```

- [ ] **Step 4: Run config verification after editing**

Run: `rg -n "advisor-service|ADVISOR_SERVICE_URL|bookstore-advisor-service" docker-compose.yml render.yaml DEPLOY_RENDER.md`
Expected: matches in all intended files.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml render.yaml DEPLOY_RENDER.md
git commit -m "chore: wire advisor service deployment"
```

### Task 11: End-to-End Verification and Demo Readiness

**Files:**
- Modify: `advisor-service/app/tests.py`
- Modify: `api-gateway/app/tests.py`
- Test: `advisor-service/app/tests.py`
- Test: `api-gateway/app/tests.py`
- Test: `docker-compose.yml`

- [ ] **Step 1: Add a final regression checklist**

```text
advisor-service health endpoint passes
behavior feature extraction passes
model wrapper passes
KB retrieval passes
advisor orchestration passes
gateway proxy passes
base template renders popup
docker-compose config includes advisor-service
```

- [ ] **Step 2: Run advisor-service test suite**

Run: `cd advisor-service; python manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 3: Run api-gateway test suite**

Run: `cd api-gateway; python manage.py test app.tests -v 2`
Expected: PASS

- [ ] **Step 4: Run a basic local compose build**

Run: `docker compose build advisor-service api-gateway`
Expected: successful image build for both services.

- [ ] **Step 5: Run a local demo smoke test**

Run: `docker compose up -d advisor-service api-gateway`
Expected: both containers start successfully.

Run: `curl http://localhost:8009/healthz/`
Expected: `{"status":"ok","service":"advisor-service"}`

Run: `curl -X POST http://localhost:8009/advisor/chat/ -H "Content-Type: application/json" -d "{\"question\":\"Recommend books for me\",\"user_id\":1}"`
Expected: JSON response with `answer`, `behavior_segment`, `recommended_books`, and `sources`.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/tests.py api-gateway/app/tests.py
git commit -m "test: verify end-to-end advisor integration"
```

## Self-Review

### Spec coverage

- New `advisor-service`: covered by Tasks 1 through 7.
- Deep learning `model_behavior`: covered by Tasks 3 and 4.
- KB for consultation: covered by Task 5.
- RAG chat flow: covered by Tasks 5 and 6.
- Popup chat in frontend: covered by Task 9.
- Integration and deployment: covered by Tasks 8, 10, and 11.

No spec section is left without an implementation task.

### Placeholder scan

- No `TODO`, `TBD`, or deferred implementation placeholders remain.
- Config review tasks are explicit and paired with exact commands.
- Test steps specify commands and expected outcomes.

### Type consistency

- Core output field names are consistent across tasks: `answer`, `behavior_segment`, `recommended_books`, `sources`, `feature_summary`.
- Gateway and advisor endpoints both use `/advisor/chat/` and `/advisor/profile/<user_id>/`.
- Model artifact names are consistent: `model_behavior.h5`, `features.txt`, `labels.txt`.
