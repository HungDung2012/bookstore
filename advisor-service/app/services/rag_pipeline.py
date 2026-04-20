import re


class HybridRAGPipeline:
    def __init__(self, graph_retriever, text_retriever):
        self.graph_retriever = graph_retriever
        self.text_retriever = text_retriever

    def _normalize_text(self, value):
        normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def _display_node_id(self, node_id):
        if not node_id:
            return ""
        node_text = str(node_id).split(":", 1)[-1]
        return node_text.replace("_", " ")

    def _block_text(self, block):
        kind = block.get("kind")
        if kind == "graph_fact":
            return block.get("text", "")
        if kind == "graph_path":
            return block.get("text", "")
        if kind == "text_source":
            return block.get("text", "")
        return block.get("text", "")

    def _block_signature(self, block):
        kind = block.get("kind", "context")
        if kind == "graph_path":
            nodes = tuple(block.get("nodes", []))
            relations = tuple(block.get("relations", []))
            return kind, nodes, relations

        parts = [
            block.get("title", ""),
            block.get("text", ""),
            block.get("node_id", ""),
            block.get("doc_type", ""),
            block.get("target_segment", ""),
        ]
        normalized = self._normalize_text(" ".join(str(part) for part in parts if part))
        tokens = tuple(sorted(token for token in normalized.split() if token))
        return kind, tokens

    def _blocks_overlap(self, left, right):
        if left.get("kind") == "graph_path" or right.get("kind") == "graph_path":
            return self._block_signature(left) == self._block_signature(right)

        left_tokens = set(self._block_signature(left)[1])
        right_tokens = set(self._block_signature(right)[1])
        if not left_tokens or not right_tokens:
            return False

        shared = left_tokens & right_tokens
        overlap = len(shared) / float(min(len(left_tokens), len(right_tokens)))
        return overlap >= 0.8

    def _block_sort_key(self, block):
        kind_priority = {
            "graph_fact": 0,
            "graph_path": 1,
            "text_source": 2,
        }.get(block.get("kind"), 3)
        score = float(block.get("score", 0.0))
        return (-score, kind_priority, block.get("title", ""), self._block_text(block))

    def _dedupe_and_order_blocks(self, blocks):
        ordered_blocks = sorted(blocks, key=self._block_sort_key)
        deduped = []
        for block in ordered_blocks:
            duplicate_index = None
            for index, existing in enumerate(deduped):
                if self._blocks_overlap(existing, block):
                    duplicate_index = index
                    break

            if duplicate_index is None:
                deduped.append(dict(block))
                continue

            existing = deduped[duplicate_index]
            existing["score"] = max(float(existing.get("score", 0.0)), float(block.get("score", 0.0)))
            existing.setdefault("source_kinds", [])
            if existing["kind"] not in existing["source_kinds"]:
                existing["source_kinds"].append(existing["kind"])
            if block.get("kind") not in existing["source_kinds"]:
                existing["source_kinds"].append(block.get("kind"))

        return deduped

    def _graph_fact_block(self, fact):
        return {
            "kind": "graph_fact",
            "id": fact.get("id"),
            "node_id": fact.get("node_id"),
            "title": fact.get("relation", "Graph fact"),
            "text": fact.get("statement", ""),
            "score": fact.get("score", 0.0),
            "reasons": list(fact.get("reasons", [])),
        }

    def _graph_path_block(self, path):
        nodes = path.get("nodes", [])
        relations = path.get("relations", [])
        path_text = " -> ".join(self._display_node_id(node) for node in nodes if node)
        return {
            "kind": "graph_path",
            "nodes": list(nodes),
            "relations": list(relations),
            "title": path_text or "Graph path",
            "text": path_text,
            "score": path.get("score", 0.0),
            "reason": path.get("reason", ""),
        }

    def _text_source_block(self, source):
        return {
            "kind": "text_source",
            "id": source.get("id"),
            "title": source.get("title", source.get("id", "Document")),
            "text": source.get("text", ""),
            "doc_type": source.get("doc_type"),
            "target_segment": source.get("target_segment"),
            "score": source.get("score", 0.0),
            "reasons": list(source.get("reasons", [])),
        }

    def retrieve(self, question, behavior_segment=None, top_k=3):
        graph_result = self.graph_retriever.search(
            question,
            behavior_segment,
            top_k=top_k,
        )
        text_sources = self.text_retriever.search(
            question,
            behavior_segment=behavior_segment,
            top_k=top_k,
        )

        graph_facts = list(graph_result.get("facts", []))
        graph_paths = list(graph_result.get("paths", []))

        context_blocks = self._dedupe_and_order_blocks(
            [
                *[self._graph_fact_block(fact) for fact in graph_facts],
                *[self._graph_path_block(path) for path in graph_paths],
                *[self._text_source_block(source) for source in text_sources],
            ]
        )

        return {
            "graph_facts": graph_facts,
            "graph_paths": graph_paths,
            "text_sources": text_sources,
            "context_blocks": context_blocks,
        }
