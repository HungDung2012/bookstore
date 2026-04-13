from collections import Counter
import re


class RetrieverService:
    def __init__(self, kb_service):
        self.kb_service = kb_service
        self.documents = kb_service.load_documents()

    def _score(self, query, document, target_segment=None):
        query_terms = Counter(re.findall(r"\w+", query.lower()))
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
