import re


class RetrieverService:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "do",
        "for",
        "is",
        "or",
        "the",
        "to",
        "what",
        "your",
    }

    def __init__(self, kb_service):
        self.kb_service = kb_service
        self.documents = kb_service.load_documents()

    def _tokenize(self, value):
        return {
            token
            for token in re.findall(r"\w+", value.lower())
            if token not in self.STOPWORDS
        }

    def _score(self, query, document, target_segment=None):
        query_terms = self._tokenize(query)
        document_terms = self._tokenize(
            f"{document.get('title', '')} {document.get('text', '')} {' '.join(document.get('tags', []))}"
        )
        score = len(query_terms & document_terms)
        if score and target_segment and document.get("target_segment") in (target_segment, "all"):
            score += 1
        return score

    def search(self, query, target_segment=None, top_k=3):
        query_terms = self._tokenize(query)
        ranked = sorted(
            self.documents,
            key=lambda doc: self._score(query, doc, target_segment=target_segment),
            reverse=True,
        )
        if not query_terms:
            return []

        return [doc for doc in ranked if self._score(query, doc, target_segment=target_segment) > 0][:top_k]
