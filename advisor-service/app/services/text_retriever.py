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

    def _segment_terms(self, value):
        if not value:
            return set()

        normalized = str(value).replace("_", " ").replace("-", " ")
        return self._tokenize(normalized)

    def _score(self, query, document, behavior_segment=None):
        query_terms = self._tokenize(query)
        document_terms = self._document_terms(document)

        overlap = sorted(query_terms & document_terms)
        score = float(len(overlap))
        reasons = []

        if overlap:
            reasons.append(f"query overlap: {', '.join(overlap)}")

        doc_type = document.get("doc_type")
        doc_type_bonus = self.DOC_TYPE_WEIGHTS.get(doc_type, 0.0)
        if doc_type_bonus:
            score += doc_type_bonus
            reasons.append(f"doc type bonus: {doc_type}")

        target_segment = document.get("target_segment")
        if target_segment == "all":
            score += 0.5
            reasons.append("broad audience bonus: all")
        elif behavior_segment and target_segment:
            behavior_terms = self._segment_terms(behavior_segment)
            target_terms = self._segment_terms(target_segment)
            segment_overlap = sorted(behavior_terms & target_terms)
            if segment_overlap:
                if str(target_segment).strip().lower() == str(behavior_segment).strip().lower():
                    segment_bonus = 2.0
                    reasons.append(f"segment match: {behavior_segment}")
                else:
                    segment_bonus = 1.0 + 0.25 * len(segment_overlap)
                    reasons.append(f"segment token overlap: {', '.join(segment_overlap)}")
                score += segment_bonus

        return score, reasons

    def search(self, question, behavior_segment=None, top_k=3):
        if not question:
            return []

        scored_documents = []
        for index, document in enumerate(self.documents):
            score, reasons = self._score(question, document, behavior_segment=behavior_segment)
            if score <= 0:
                continue
            scored_documents.append((score, index, document, reasons))

        ranked_documents = sorted(scored_documents, key=lambda item: (-item[0], item[1]))

        results = []
        for score, _, document, reasons in ranked_documents:
            result = dict(document)
            result["score"] = round(score, 3)
            result["reasons"] = list(reasons)
            results.append(result)
            if len(results) >= top_k:
                break

        return results
