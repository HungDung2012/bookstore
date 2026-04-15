import re


class TextRetriever:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "do",
        "for",
        "how",
        "i",
        "is",
        "me",
        "of",
        "the",
        "to",
        "what",
        "work",
        "working",
        "you",
    }

    DOC_TYPE_WEIGHTS = {
        "segment_advice": 1.5,
        "faq": 1.0,
        "policy": 0.75,
        "category": 0.5,
    }

    def __init__(self, kb_service):
        self.kb_service = kb_service
        self.documents = kb_service.load_documents()

    def _tokenize(self, value):
        if not value:
            return set()

        return {
            token
            for token in re.findall(r"\w+", str(value).lower())
            if token not in self.STOPWORDS
        }

    def _document_terms(self, document):
        tags = document.get("tags") or []
        metadata = [
            document.get("title", ""),
            document.get("text", ""),
            " ".join(tags),
            document.get("doc_type", ""),
            document.get("category", ""),
            document.get("target_segment", ""),
        ]
        return set().union(*(self._tokenize(field) for field in metadata))

    def _score(self, query, document, behavior_segment=None):
        query_terms = self._tokenize(query)
        document_terms = self._document_terms(document)

        overlap = len(query_terms & document_terms)
        if not overlap:
            return 0.0

        score = float(overlap)

        doc_type = document.get("doc_type")
        score += self.DOC_TYPE_WEIGHTS.get(doc_type, 0.0)

        target_segment = document.get("target_segment")
        if behavior_segment and target_segment == behavior_segment:
            score += 2.0
        elif target_segment == "all":
            score += 0.5

        if behavior_segment:
            score += 0.25 * len({behavior_segment} & self._tokenize(target_segment))

        return score

    def search(self, question, behavior_segment=None, top_k=3):
        if not question:
            return []

        ranked_documents = sorted(
            enumerate(self.documents),
            key=lambda item: (
                self._score(question, item[1], behavior_segment=behavior_segment),
                -item[0],
            ),
            reverse=True,
        )

        results = []
        for _, document in ranked_documents:
            if self._score(question, document, behavior_segment=behavior_segment) <= 0:
                continue
            results.append(document)
            if len(results) >= top_k:
                break

        return results
