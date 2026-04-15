import re


class GraphRetriever:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "can",
        "do",
        "for",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }

    CATEGORY_KEYWORDS = {
        "programming": {"programming", "coding", "code", "developer", "software", "python", "data", "tech"},
        "literature": {"literature", "fiction", "novel", "novels", "classic", "classics", "essay", "essays", "reading"},
        "children": {"children", "child", "kids", "kid", "family", "storybook", "storybooks", "read-aloud"},
    }

    SERVICE_KEYWORDS = {
        "payment": {"payment", "checkout", "billing", "pay", "card", "charge", "order"},
        "shipping": {"shipping", "delivery", "deliver", "tracking", "shipment", "mail", "arrival", "fulfillment"},
    }

    POLICY_KEYWORDS = {
        "cancellation": {"cancellation", "cancel", "returns", "return", "refund", "refunds", "policy"},
    }

    def __init__(self, graph):
        self.graph = graph

    def _tokenize(self, value):
        normalized = (value or "").lower().replace("’", "'").replace("`", "'")
        tokens = set()
        for raw_token in re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", normalized):
            token = raw_token
            if token.endswith("'s"):
                token = token[:-2]
            elif token.endswith("'"):
                token = token[:-1]
            if token and token not in self.STOPWORDS:
                tokens.add(token)
        return tokens

    def _node_tokens(self, node):
        metadata_text = " ".join(str(value) for value in (node.metadata or {}).values())
        return self._tokenize(f"{node.id} {node.type} {node.label} {metadata_text}")

    def _edge_between(self, source, target):
        for edge in self.graph.edges_for_node(source)["outgoing"]:
            if edge.target == target:
                return edge
        return None

    def _segment_node_id(self, behavior_segment):
        if not behavior_segment:
            return None
        return f"segment:{behavior_segment.strip()}"

    def _type_keyword_hits(self, node, question_tokens):
        node_suffix = node.id.split(":", 1)[-1]
        if node.type == "category":
            keywords = self.CATEGORY_KEYWORDS.get(node_suffix, set())
        elif node.type == "service":
            keywords = self.SERVICE_KEYWORDS.get(node_suffix, set())
        elif node.type == "policy":
            keywords = self.POLICY_KEYWORDS.get(node_suffix, set())
        else:
            keywords = set()
        return sorted(question_tokens & keywords)

    def _score_node(self, question_tokens, behavior_segment, node):
        score = 0.0
        reasons = []
        segment_node_id = self._segment_node_id(behavior_segment)

        query_overlap = sorted(question_tokens & self._node_tokens(node))
        if query_overlap:
            score += len(query_overlap)
            reasons.append(f"query overlap: {', '.join(query_overlap)}")

        if segment_node_id and node.id == segment_node_id:
            score += 5.0
            reasons.append(f"behavior segment match: {behavior_segment}")

        if segment_node_id:
            edge = self._edge_between(segment_node_id, node.id)
            if edge:
                score += 2.0 + float(edge.weight)
                reasons.append(f"direct graph link: {edge.relation}")

        type_hits = self._type_keyword_hits(node, question_tokens)
        if type_hits:
            score += 2.5 + 0.5 * len(type_hits)
            reasons.append(f"{node.type} keyword overlap: {', '.join(type_hits)}")

        if node.type == "segment" and behavior_segment:
            segment_key = node.id.split(":", 1)[-1]
            segment_tokens = self._tokenize(f"{segment_key} {node.label} {(node.metadata or {}).get('description', '')}")
            segment_hits = sorted(question_tokens & segment_tokens)
            if segment_hits:
                score += 1.5 + 0.5 * len(segment_hits)
                reasons.append(f"segment context overlap: {', '.join(segment_hits)}")

        return score, reasons

    def _build_fact_result(self, fact, node_score, question_tokens, reasons):
        fact_tokens = self._tokenize(fact.statement)
        fact_overlap = sorted(question_tokens & fact_tokens)
        confidence = str((fact.metadata or {}).get("confidence", "")).lower()
        confidence_bonus = {"high": 0.5, "medium": 0.25}.get(confidence, 0.0)
        return {
            "id": fact.id,
            "node_id": fact.node_id,
            "relation": fact.relation,
            "statement": fact.statement,
            "score": round(node_score + len(fact_overlap) + confidence_bonus, 3),
            "reasons": list(reasons) + ([f"fact overlap: {', '.join(fact_overlap)}"] if fact_overlap else []),
        }

    def _build_direct_path(self, segment_node_id, target_node_id, node_score, reasons):
        edge = self._edge_between(segment_node_id, target_node_id)
        if not edge:
            return None
        return {
            "nodes": [segment_node_id, target_node_id],
            "relations": [edge.relation],
            "score": round(node_score + float(edge.weight), 3),
            "reason": "; ".join(reasons) if reasons else edge.relation,
        }

    def _build_two_hop_paths(self, segment_node_id, node, node_score, question_tokens, reasons):
        paths = []
        if node.type != "category":
            return paths

        segment_edge = self._edge_between(segment_node_id, node.id)
        if not segment_edge:
            return paths

        for edge in self.graph.edges_for_node(node.id)["outgoing"]:
            if edge.target not in self.graph.nodes:
                continue
            target_node = self.graph.nodes[edge.target]
            target_hits = self._type_keyword_hits(target_node, question_tokens)
            if target_node.type not in {"service", "policy"}:
                continue
            if not target_hits:
                continue

            paths.append(
                {
                    "nodes": [segment_node_id, node.id, target_node.id],
                    "relations": [segment_edge.relation, edge.relation],
                    "score": round(node_score + float(segment_edge.weight) + float(edge.weight), 3),
                    "reason": "; ".join(reasons) if reasons else f"{segment_edge.relation} -> {edge.relation}",
                }
            )
        return paths

    def search(self, question, behavior_segment, top_k=5):
        question_tokens = self._tokenize(question)
        if not question_tokens and not behavior_segment:
            return {"facts": [], "paths": []}

        scored_nodes = []
        for node in self.graph.nodes.values():
            score, reasons = self._score_node(question_tokens, behavior_segment, node)
            if score > 0:
                scored_nodes.append((score, node, reasons))

        scored_nodes.sort(key=lambda item: (-item[0], item[1].id))
        ranked_nodes = scored_nodes[: max(top_k * 2, top_k)]

        ranked_facts = []
        for score, node, reasons in ranked_nodes:
            for fact in self.graph.facts_for_node(node.id):
                ranked_facts.append(self._build_fact_result(fact, score, question_tokens, reasons))

        ranked_facts.sort(key=lambda item: (-item["score"], item["node_id"], item["id"]))

        ranked_paths = []
        segment_node_id = self._segment_node_id(behavior_segment)
        if segment_node_id and segment_node_id in self.graph.nodes:
            for score, node, reasons in ranked_nodes:
                direct_path = self._build_direct_path(segment_node_id, node.id, score, reasons)
                if direct_path:
                    ranked_paths.append(direct_path)
                ranked_paths.extend(self._build_two_hop_paths(segment_node_id, node, score, question_tokens, reasons))

        # Deduplicate paths while preserving score order.
        unique_paths = []
        seen = set()
        for path in sorted(ranked_paths, key=lambda item: (-item["score"], item["nodes"], item["relations"])):
            key = (tuple(path["nodes"]), tuple(path["relations"]))
            if key in seen:
                continue
            seen.add(key)
            unique_paths.append(path)

        return {
            "facts": ranked_facts[:top_k],
            "paths": unique_paths[:top_k],
            "matched_nodes": [
                {
                    "id": node.id,
                    "score": round(score, 3),
                    "reasons": list(reasons),
                }
                for score, node, reasons in ranked_nodes[:top_k]
            ],
        }
