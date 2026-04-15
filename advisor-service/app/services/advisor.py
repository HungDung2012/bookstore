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
            filtered = [book for book in (books or []) if book.get("category") == 3]
        elif segment == "literature_reader":
            filtered = [book for book in (books or []) if book.get("category") == 5]
        else:
            filtered = books or []
        return filtered[:limit]

    def _call_llm(self, prompt):
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if not api_key:
            return None

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _collect_behavior_inputs(self, user_id=None):
        books = self.client.get_books()
        if user_id is None:
            profile = {"id": user_id}
            orders = []
            reviews = []
            cart_items = []
        else:
            profile = self.client.get_user(user_id)
            orders = self.client.get_orders(user_id)
            reviews = self.client.get_reviews(user_id)
            cart_items = self.client.get_cart(user_id)
        return books, profile, orders, reviews, cart_items

    def _predict_behavior(self, profile, books, orders, reviews, cart_items):
        features = build_behavior_features(profile, books, orders, reviews, cart_items)
        prediction = self.model_service.predict(features)
        return features, prediction

    def _profile_fallback_payload(self):
        return {
            "behavior_segment": "casual_buyer",
            "feature_summary": "Profile unavailable; using fallback behavior segment.",
        }

    def chat(self, user_id=None, question=""):
        books, profile, orders, reviews, cart_items = self._collect_behavior_inputs(user_id)

        features, prediction = self._predict_behavior(profile, books, orders, reviews, cart_items)
        behavior_segment = prediction["behavior_segment"]
        recommended_books = self._pick_books(books, behavior_segment)
        sources = self.retriever.search(question, target_segment=behavior_segment, top_k=3)
        feature_summary = (
            f"Predicted segment is {behavior_segment} from orders={features['order_count']}, "
            f"reviews={features['review_count']}."
        )
        prompt = build_chat_prompt(
            question,
            behavior_segment,
            feature_summary,
            sources,
            recommended_books,
        )

        try:
            answer = self._call_llm(prompt) or build_fallback_answer(
                question,
                behavior_segment,
                recommended_books,
            )
        except Exception:
            answer = build_fallback_answer(question, behavior_segment, recommended_books)

        return {
            "answer": answer,
            "behavior_segment": behavior_segment,
            "recommended_books": recommended_books,
            "sources": sources,
            "feature_summary": feature_summary,
        }

    def profile(self, user_id):
        try:
            books, profile, orders, reviews, cart_items = self._collect_behavior_inputs(user_id)
            features, prediction = self._predict_behavior(
                profile,
                books,
                orders,
                reviews,
                cart_items,
            )
            prediction["feature_summary"] = (
                f"Predicted segment is {prediction['behavior_segment']} from "
                f"{features['order_count']} orders and {features['review_count']} reviews."
            )
            return prediction
        except Exception:
            return self._profile_fallback_payload()
