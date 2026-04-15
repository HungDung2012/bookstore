class HybridRAGPipeline:
    def __init__(self, graph_retriever, text_retriever):
        self.graph_retriever = graph_retriever
        self.text_retriever = text_retriever

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
        return {
            "kind": "graph_path",
            "nodes": list(nodes),
            "relations": list(relations),
            "title": "Graph path",
            "text": " -> ".join(nodes) if nodes else "",
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

        context_blocks = []
        context_blocks.extend(self._graph_fact_block(fact) for fact in graph_facts)
        context_blocks.extend(self._graph_path_block(path) for path in graph_paths)
        context_blocks.extend(self._text_source_block(source) for source in text_sources)

        return {
            "graph_facts": graph_facts,
            "graph_paths": graph_paths,
            "text_sources": text_sources,
            "context_blocks": context_blocks,
        }
