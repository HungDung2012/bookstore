import os

import requests

from .behavior_model import BehaviorModelService
from .clients import UpstreamClient
from .features import build_behavior_features
from .graph_kb import GraphKnowledgeBase
from .graph_retriever import GraphRetriever
from .knowledge_base import KnowledgeBaseService
from .rag_pipeline import HybridRAGPipeline
from .prompting import build_chat_prompt, build_fallback_answer
from .text_retriever import TextRetriever


class AdvisorService:
    def __init__(self):
        self.client = UpstreamClient()
        self.model_service = BehaviorModelService()
        self.text_kb = KnowledgeBaseService("app/data/knowledge_base")
        self.graph_kb = GraphKnowledgeBase("app/data/knowledge_graph")
        self.text_retriever = TextRetriever(self.text_kb)
        self.graph_retriever = GraphRetriever(self.graph_kb)
        self.rag_pipeline = HybridRAGPipeline(self.graph_retriever, self.text_retriever)

    def _book_category(self, book):
        try:
            return int(book.get("category"))
        except (TypeError, ValueError, AttributeError):
            return None

    def _book_price(self, book):
        try:
            return float(book.get("price"))
        except (TypeError, ValueError, AttributeError):
            return float("inf")

    def _filter_books_by_categories(self, books, categories):
        prioritized = []
        remaining = []
        for book in books or []:
            category = self._book_category(book)
            if category in categories:
                prioritized.append(book)
            else:
                remaining.append(book)
        prioritized.sort(key=lambda book: (categories.index(self._book_category(book)), self._book_price(book), str(book.get("title", ""))))
        remaining.sort(key=lambda book: (self._book_price(book), str(book.get("title", ""))))
        return [*prioritized, *remaining]

    def _pick_books(self, books, segment, limit=3):
        books = books or []
        segment = str(segment or "").strip()
        if segment == "impulse_buyer":
            filtered = self._filter_books_by_categories(books, [3])
        elif segment == "careful_researcher":
            filtered = self._filter_books_by_categories(books, [5])
        elif segment == "discount_hunter":
            filtered = sorted(
                books,
                key=lambda book: (self._book_price(book), self._book_category(book) or 0, str(book.get("title", ""))),
            )
        elif segment == "loyal_reader":
            filtered = self._filter_books_by_categories(books, [5, 3])
        elif segment == "window_shopper":
            filtered = self._filter_books_by_categories(books, [8, 5, 3, 7])
        else:
            filtered = sorted(books, key=lambda book: (self._book_category(book) or 0, self._book_price(book), str(book.get("title", ""))))
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

    def _build_feature_summary(self, features, prediction):
        behavior_segment = prediction.get("behavior_segment", "casual_buyer")
        model_name = prediction.get("model_name", "unknown_model")
        orders = features.get("order_count", 0)
        reviews = features.get("review_count", 0)
        cart_items = features.get("cart_item_count", 0)
        summary = (
            f"Predicted segment is {behavior_segment} with {model_name} from orders={orders}, "
            f"reviews={reviews}, cart_items={cart_items}."
        )

        sequence_summary = prediction.get("sequence_summary") or {}
        if sequence_summary:
            summary = (
                f"{summary} Sequence length={sequence_summary.get('sequence_length', 0)}, "
                f"encoder_available={sequence_summary.get('encoder_available', False)}."
            )

        probabilities = prediction.get("probabilities") or {}
        if probabilities:
            ranked_probabilities = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))[:3]
            top_signals = ", ".join(f"{label}={prob:.2f}" for label, prob in ranked_probabilities)
            summary = f"{summary} Top probabilities: {top_signals}."

        return summary

    def _chat_fallback_payload(self, question=""):
        behavior_segment = "casual_buyer"
        recommended_books = []
        return {
            "answer": build_fallback_answer(question, behavior_segment, recommended_books),
            "behavior_segment": behavior_segment,
            "probabilities": {},
            "recommended_books": recommended_books,
            "sources": [],
            "graph_facts": [],
            "graph_paths": [],
            "context_blocks": [],
            "model_name": "fallback",
            "sequence_summary": {
                "model_name": "fallback",
                "sequence_length": 0,
                "feature_dim": 0,
                "profile_fields": [],
                "step_fields": [],
                "encoder_available": False,
            },
            "feature_summary": "Chat unavailable; using fallback behavior segment.",
        }

    def _profile_fallback_payload(self):
        return {
            "behavior_segment": "casual_buyer",
            "probabilities": {},
            "recommended_books": [],
            "sources": [],
            "graph_facts": [],
            "graph_paths": [],
            "context_blocks": [],
            "model_name": "fallback",
            "sequence_summary": {
                "model_name": "fallback",
                "sequence_length": 0,
                "feature_dim": 0,
                "profile_fields": [],
                "step_fields": [],
                "encoder_available": False,
            },
            "feature_summary": "Profile unavailable; using fallback behavior segment.",
        }

    def chat(self, user_id=None, question=""):
        try:
            books, profile, orders, reviews, cart_items = self._collect_behavior_inputs(user_id)

            features, prediction = self._predict_behavior(profile, books, orders, reviews, cart_items)
            behavior_segment = prediction["behavior_segment"]
            model_name = prediction.get("model_name", "unknown_model")
            sequence_summary = prediction.get("sequence_summary") or {}
            recommended_books = self._pick_books(books, behavior_segment)
            retrieval = self.rag_pipeline.retrieve(question, behavior_segment=behavior_segment, top_k=3)
            sources = retrieval["text_sources"]
            feature_summary = self._build_feature_summary(features, prediction)
            prompt = build_chat_prompt(
                question,
                behavior_segment,
                feature_summary,
                recommended_books=recommended_books,
                retrieval_context=retrieval,
            )

            try:
                answer = self._call_llm(prompt) or build_fallback_answer(
                    question,
                    behavior_segment,
                    recommended_books,
                    graph_facts=retrieval["graph_facts"],
                    graph_paths=retrieval["graph_paths"],
                )
            except Exception:
                answer = build_fallback_answer(
                    question,
                    behavior_segment,
                    recommended_books,
                    graph_facts=retrieval["graph_facts"],
                    graph_paths=retrieval["graph_paths"],
                )

            return {
                "answer": answer,
                "behavior_segment": behavior_segment,
                "probabilities": prediction.get("probabilities", {}),
                "recommended_books": recommended_books,
                "model_name": model_name,
                "sequence_summary": sequence_summary,
                "sources": sources,
                "graph_facts": retrieval["graph_facts"],
                "graph_paths": retrieval["graph_paths"],
                "context_blocks": retrieval["context_blocks"],
                "feature_summary": feature_summary,
            }
        except Exception:
            return self._chat_fallback_payload(question)

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
            behavior_segment = prediction["behavior_segment"]
            profile_question = f"Advice for {behavior_segment.replace('_', ' ')} readers"
            retrieval = self.rag_pipeline.retrieve(
                profile_question,
                behavior_segment=behavior_segment,
                top_k=3,
            )
            prediction["feature_summary"] = self._build_feature_summary(features, prediction)
            prediction["recommended_books"] = self._pick_books(books, behavior_segment)
            prediction["sources"] = retrieval["text_sources"]
            prediction["graph_facts"] = retrieval["graph_facts"]
            prediction["graph_paths"] = retrieval["graph_paths"]
            prediction["context_blocks"] = retrieval["context_blocks"]
            return prediction
        except Exception:
            return self._profile_fallback_payload()
