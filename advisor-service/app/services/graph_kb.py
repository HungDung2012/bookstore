import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    label: str
    metadata: dict


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GraphFact:
    id: str
    node_id: str
    relation: str
    statement: str
    metadata: dict


SEGMENT_NODE_TARGETS = {
    "impulse_buyer": [
        ("category:programming", "prefers_fast_discovery", 0.9),
        ("service:payment", "needs_fast_checkout", 0.75),
    ],
    "careful_researcher": [
        ("category:literature", "prefers_deep_reading", 0.95),
        ("service:shipping", "waits_for_reliable_delivery", 0.62),
    ],
    "discount_hunter": [
        ("service:shipping", "optimizes_cost", 0.88),
        ("policy:cancellation", "checks_before_buying", 0.74),
    ],
    "loyal_reader": [
        ("category:literature", "prefers_repeated_browsing", 0.96),
        ("service:shipping", "wants_consistent_delivery", 0.64),
    ],
    "window_shopper": [
        ("category:business", "compares_options_broadly", 0.7),
        ("service:payment", "keeps_checkout_simple", 0.55),
    ],
}

SEGMENT_FACT_STATEMENTS = {
    "impulse_buyer": "Impulse buyers move quickly from browsing to cart and value low-friction checkout.",
    "careful_researcher": "Careful researchers compare details, revisit pages, and prefer structured buying decisions.",
    "discount_hunter": "Discount hunters compare pricing, shipping costs, and cancellation flexibility before buying.",
    "loyal_reader": "Loyal readers repeatedly revisit familiar categories and keep reading-focused shopping loops.",
    "window_shopper": "Window shoppers browse widely, compare options, and often leave before checkout.",
}

BOOK_CATEGORY_ALIASES = {
    3: "programming",
    5: "literature",
    7: "children",
    8: "business",
}

ROW_CATEGORY_ALIASES = {
    "technology": "programming",
    "electronics": "programming",
    "programming": "programming",
    "data": "programming",
    "python": "programming",
    "literature": "literature",
    "fiction": "literature",
    "books": "literature",
    "read": "literature",
    "children": "children",
    "family": "children",
    "story": "children",
    "storybooks": "children",
    "business": "business",
    "discounts": "business",
    "deals": "business",
    "general": "business",
    "novelty": "business",
}

CATEGORY_RELATION_TARGETS = {
    "programming": [
        ("service:payment", "often_pairs_with", 0.42),
    ],
    "literature": [
        ("service:shipping", "often_requires", 0.5),
    ],
    "children": [
        ("policy:cancellation", "benefits_from", 0.55),
    ],
    "business": [
        ("service:shipping", "optimizes_cost", 0.4),
        ("policy:cancellation", "checks_before_buying", 0.36),
    ],
}

SEQUENCE_FIELDS = [
    *[f"step_{index}_behavior" for index in range(1, 9)],
    *[f"step_{index}_category" for index in range(1, 9)],
    *[f"step_{index}_price_band" for index in range(1, 9)],
    *[f"step_{index}_duration" for index in range(1, 9)],
]


class GraphKnowledgeBase:
    _APP_ROOT = Path(__file__).resolve().parents[2]

    def __init__(self, base_path):
        base_path = Path(base_path)
        self.base_path = base_path if base_path.is_absolute() else self._APP_ROOT / base_path

        self.nodes = self._load_nodes()
        self.edges = self._load_edges()
        self.facts = self._load_facts()
        self.adjacency = self._build_adjacency()

    @staticmethod
    def _clean_metadata(metadata):
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _as_node(item):
        metadata = GraphKnowledgeBase._clean_metadata(item.get("metadata") or {})
        return GraphNode(
            id=str(item.get("id", "")).strip(),
            type=str(item.get("type", "")).strip(),
            label=str(item.get("label", "")).strip(),
            metadata=metadata,
        )

    @staticmethod
    def _as_edge(item):
        metadata = GraphKnowledgeBase._clean_metadata(item.get("metadata") or {})
        weight = item.get("weight", 1.0)
        if weight is None:
            weight = 1.0
        return GraphEdge(
            source=str(item.get("source", "")).strip(),
            target=str(item.get("target", "")).strip(),
            relation=str(item.get("relation", "")).strip(),
            weight=float(weight),
            metadata=metadata,
        )

    @staticmethod
    def _as_fact(item):
        metadata = GraphKnowledgeBase._clean_metadata(item.get("metadata") or {})
        return GraphFact(
            id=str(item.get("id", "")).strip(),
            node_id=str(item.get("node_id", "")).strip(),
            relation=str(item.get("relation", "")).strip(),
            statement=str(item.get("statement", "")).strip(),
            metadata=metadata,
        )

    def _read_json(self, filename):
        path = self.base_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Graph knowledge base file not found: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Graph knowledge base file is not valid JSON: {path}") from exc

        if not isinstance(payload, list):
            raise ValueError(f"Graph knowledge base file must contain a JSON array: {path}")

        return payload

    def _require_nonblank_string(self, item, field_name, record_type):
        value = item.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{record_type} record must include a non-blank '{field_name}'")
        return value.strip()

    @staticmethod
    def _normalize_category_suffix(value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric = int(value)
            if float(value) != float(numeric):
                return None
            return BOOK_CATEGORY_ALIASES.get(numeric, str(numeric))

        text = str(value).strip().lower()
        if not text:
            return None
        while text.startswith("category:"):
            text = text.split(":", 1)[1].strip()
        if not text:
            return None
        if text.isdigit():
            numeric = int(text)
            return BOOK_CATEGORY_ALIASES.get(numeric, text)
        return ROW_CATEGORY_ALIASES.get(text, text.replace(" ", "_"))

    @classmethod
    def _nodes_from_records(cls, records):
        nodes = {}
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Node record must be a JSON object")
            node = cls._as_node(item)
            if not node.id:
                raise ValueError("Node record must include a non-blank 'id'")
            if node.id in nodes:
                raise ValueError(f"Duplicate node id: {node.id}")
            nodes[node.id] = node
        return nodes

    @classmethod
    def _edges_from_records(cls, records, nodes):
        edges = []
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Edge record must be a JSON object")
            edge = cls._as_edge(item)
            if not edge.source:
                raise ValueError("Edge record must include a non-blank 'source'")
            if not edge.target:
                raise ValueError("Edge record must include a non-blank 'target'")
            if not edge.relation:
                raise ValueError("Edge record must include a non-blank 'relation'")
            edges.append(edge)

        for edge in edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError(
                    f"Edge endpoints must reference existing nodes: {edge.source} -> {edge.target}"
                )
        return edges

    @classmethod
    def _facts_from_records(cls, records, nodes):
        facts = []
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Fact record must be a JSON object")
            fact = cls._as_fact(item)
            if not fact.id:
                raise ValueError("Fact record must include a non-blank 'id'")
            if not fact.node_id:
                raise ValueError("Fact record must include a non-blank 'node_id'")
            if not fact.relation:
                raise ValueError("Fact record must include a non-blank 'relation'")
            if not fact.statement:
                raise ValueError("Fact record must include a non-blank 'statement'")
            if fact.node_id not in nodes:
                raise ValueError(f"Fact node_id must reference an existing node: {fact.node_id}")
            facts.append(fact)
        return facts

    def _load_nodes(self):
        return self._nodes_from_records(self._read_json("nodes.json"))

    def _load_edges(self):
        return self._edges_from_records(self._read_json("edges.json"), self.nodes)

    def _load_facts(self):
        return self._facts_from_records(self._read_json("facts.json"), self.nodes)

    def _build_adjacency(self):
        adjacency = {
            node_id: {"outgoing": [], "incoming": []}
            for node_id in self.nodes
        }
        for edge in self.edges:
            adjacency.setdefault(edge.source, {"outgoing": [], "incoming": []})["outgoing"].append(edge)
            adjacency.setdefault(edge.target, {"outgoing": [], "incoming": []})["incoming"].append(edge)
        return adjacency

    @classmethod
    def from_payload(cls, payload):
        instance = cls.__new__(cls)
        instance.base_path = None
        instance.nodes = cls._nodes_from_records(payload.get("nodes", []))
        instance.edges = cls._edges_from_records(payload.get("edges", []), instance.nodes)
        instance.facts = cls._facts_from_records(payload.get("facts", []), instance.nodes)
        instance.adjacency = instance._build_adjacency()
        return instance

    @staticmethod
    def _node_dict(node_id, node_type, label, metadata=None):
        return {
            "id": node_id,
            "type": node_type,
            "label": label,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    @staticmethod
    def _edge_dict(source, target, relation, weight=1.0, metadata=None):
        return {
            "source": source,
            "target": target,
            "relation": relation,
            "weight": float(weight),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    @staticmethod
    def _fact_dict(fact_id, node_id, relation, statement, metadata=None):
        return {
            "id": fact_id,
            "node_id": node_id,
            "relation": relation,
            "statement": statement,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    @classmethod
    def build_export_payload(cls, rows, books):
        rows = [row for row in rows if isinstance(row, dict)]
        books = [book for book in books if isinstance(book, dict)]

        nodes = {}
        edges = []
        facts = []
        segment_rows = {}
        segment_category_counter = {}
        segment_behavior_counter = {}
        segment_price_counter = {}
        row_count = 0
        step_behavior_fields = [f"step_{index}_behavior" for index in range(1, 9)]
        step_category_fields = [f"step_{index}_category" for index in range(1, 9)]
        step_price_fields = [f"step_{index}_price_band" for index in range(1, 9)]

        def upsert_node(node_id, node_type, label, metadata=None):
            existing = nodes.get(node_id)
            metadata = metadata if isinstance(metadata, dict) else {}
            if existing is None:
                nodes[node_id] = cls._node_dict(node_id, node_type, label, metadata)
                return nodes[node_id]

            merged_metadata = dict(existing["metadata"])
            merged_metadata.update(metadata)
            existing["metadata"] = merged_metadata
            if label and not existing.get("label"):
                existing["label"] = label
            if node_type and not existing.get("type"):
                existing["type"] = node_type
            return existing

        def add_edge(source, target, relation, weight=1.0, metadata=None):
            if not source or not target:
                return
            metadata = metadata if isinstance(metadata, dict) else {}
            for edge in edges:
                if edge["source"] == source and edge["target"] == target and edge["relation"] == relation:
                    edge["weight"] = max(float(edge["weight"]), float(weight))
                    merged_metadata = dict(edge["metadata"])
                    merged_metadata.update(metadata)
                    edge["metadata"] = merged_metadata
                    return
            edges.append(cls._edge_dict(source, target, relation, weight, metadata))

        def add_fact(fact_id, node_id, relation, statement, metadata=None):
            if not fact_id or not node_id or not statement:
                return
            for fact in facts:
                if fact["id"] == fact_id:
                    merged_metadata = dict(fact["metadata"])
                    merged_metadata.update(metadata if isinstance(metadata, dict) else {})
                    fact["metadata"] = merged_metadata
                    fact["statement"] = statement
                    return
            facts.append(cls._fact_dict(fact_id, node_id, relation, statement, metadata))

        def segment_label(value):
            value = str(value or "").strip()
            return value or "window_shopper"

        for row in rows:
            row_count += 1
            label = segment_label(row.get("label"))
            user_id = str(row.get("user_id", "")).strip()
            if not user_id:
                continue

            segment_node_id = f"segment:{label}"
            favorite_category = cls._normalize_category_suffix(row.get("favorite_category"))
            step_categories = [cls._normalize_category_suffix(row.get(field)) for field in step_category_fields]
            step_categories = [category for category in step_categories if category]
            category_counts = Counter([favorite_category, *step_categories] if favorite_category else step_categories)
            behavior_sequence = [str(row.get(field, "")).strip() for field in step_behavior_fields if str(row.get(field, "")).strip()]
            price_bands = [str(row.get(field, "")).strip() for field in step_price_fields if str(row.get(field, "")).strip()]
            segment_category_counter.setdefault(label, Counter()).update(category_counts)
            segment_behavior_counter.setdefault(label, Counter()).update(behavior_sequence)
            segment_price_counter.setdefault(label, Counter()).update(price_bands)
            top_categories = [category for category, _ in category_counts.most_common(3)]
            top_behaviors = [behavior for behavior, _ in segment_behavior_counter[label].most_common(3)]
            top_price_bands = [band for band, _ in segment_price_counter[label].most_common(3)]
            profile_metadata = {
                "user_id": user_id,
                "age_group": str(row.get("age_group", "")).strip(),
                "favorite_category": str(row.get("favorite_category", "")).strip(),
                "price_sensitivity": str(row.get("price_sensitivity", "")).strip(),
                "membership_tier": str(row.get("membership_tier", "")).strip(),
                "label": label,
                "sequence_length": len(step_behavior_fields),
                "step_behaviors": behavior_sequence,
                "step_categories": step_categories,
                "step_price_bands": price_bands,
            }
            upsert_node(
                f"user:{user_id}",
                "user",
                f"User {user_id}",
                profile_metadata,
            )
            upsert_node(
                segment_node_id,
                "segment",
                label.replace("_", " ").title(),
                {
                    "label": label,
                    "description": SEGMENT_FACT_STATEMENTS.get(label, label.replace("_", " ").title()),
                    "row_count": 1,
                },
            )
            add_edge(
                f"user:{user_id}",
                segment_node_id,
                "classified_as",
                1.0,
                {"source": "behavior_sequence"},
            )

            if favorite_category:
                category_node_id = f"category:{favorite_category}"
                upsert_node(
                    category_node_id,
                    "category",
                    favorite_category.replace("_", " ").title(),
                    {"source": "profile_field"},
                )
                add_edge(
                    f"user:{user_id}",
                    category_node_id,
                    "prefers_category",
                    0.8,
                    {"source": "favorite_category"},
                )
            for category in step_categories[:3]:
                category_node_id = f"category:{category}"
                upsert_node(
                    category_node_id,
                    "category",
                    category.replace("_", " ").title(),
                    {"source": "sequence_step"},
                )
                add_edge(
                    f"user:{user_id}",
                    category_node_id,
                    "engages_with",
                    0.4,
                    {"source": "step_category"},
                )

            segment_rows.setdefault(label, []).append(row)

        for label, label_rows in segment_rows.items():
            segment_node_id = f"segment:{label}"
            category_counter = segment_category_counter.get(label, Counter())
            behavior_counter = segment_behavior_counter.get(label, Counter())
            price_counter = segment_price_counter.get(label, Counter())
            top_categories = [value for value, _ in category_counter.most_common(3)]
            top_behaviors = [value for value, _ in behavior_counter.most_common(3)]
            top_price_bands = [value for value, _ in price_counter.most_common(3)]
            dominant_category = top_categories[0] if top_categories else None
            segment_metadata = {
                "row_count": len(label_rows),
                "top_categories": top_categories,
                "top_behaviors": top_behaviors,
                "top_price_bands": top_price_bands,
                "dominant_category": dominant_category,
                "description": SEGMENT_FACT_STATEMENTS.get(label, label.replace("_", " ").title()),
            }
            upsert_node(
                segment_node_id,
                "segment",
                label.replace("_", " ").title(),
                segment_metadata,
            )
            if top_behaviors:
                add_fact(
                    f"fact-{label}-sequence",
                    segment_node_id,
                    "sequence_summary",
                    f"{label.replace('_', ' ').title()} rows most often begin with {top_behaviors[0].replace('_', ' ')} and center on {', '.join(top_categories[:2]) or 'mixed categories'}.",
                    {
                        "confidence": "medium",
                        "top_behaviors": top_behaviors[:3],
                        "top_categories": top_categories[:3],
                    },
                )
            add_fact(
                f"fact-{label}-summary",
                segment_node_id,
                "segment_summary",
                SEGMENT_FACT_STATEMENTS.get(label, label.replace("_", " ").title()),
                {
                    "confidence": "high",
                    "row_count": len(label_rows),
                    "top_categories": top_categories[:3],
                },
            )

            for target_node_id, relation, weight in SEGMENT_NODE_TARGETS.get(label, []):
                target_type, target_suffix = target_node_id.split(":", 1)
                upsert_node(
                    target_node_id,
                    target_type,
                    target_suffix.replace("_", " ").title(),
                    {"source": "segment_target"},
                )
                add_edge(
                    segment_node_id,
                    target_node_id,
                    relation,
                    weight,
                    {"source": "segment_target"},
                )
            for category in top_categories[:2]:
                target_node_id = f"category:{category}"
                target_type, target_suffix = target_node_id.split(":", 1)
                upsert_node(
                    target_node_id,
                    target_type,
                    target_suffix.replace("_", " ").title(),
                    {"source": "segment_profile"},
                )
                add_edge(
                    segment_node_id,
                    target_node_id,
                    "prefers_category",
                    0.85,
                    {"source": "sequence_rows"},
                )

        for book in books:
            book_id = str(book.get("id", "")).strip()
            if not book_id:
                continue
            title = str(book.get("title", "")).strip() or f"Book {book_id}"
            category_alias = cls._normalize_category_suffix(book.get("category"))
            category_node_id = f"category:{category_alias}" if category_alias else None
            book_node_id = f"book:{book_id}"
            upsert_node(
                book_node_id,
                "book",
                title,
                {
                    "title": title,
                    "price": book.get("price"),
                    "category": book.get("category"),
                },
            )
            if category_node_id:
                target_type, target_suffix = category_node_id.split(":", 1)
                upsert_node(
                    category_node_id,
                    target_type,
                    target_suffix.replace("_", " ").title(),
                    {"source": "book_catalog"},
                )
                add_edge(
                    book_node_id,
                    category_node_id,
                    "categorized_as",
                    1.0,
                    {"source": "book_catalog"},
                )
                add_fact(
                    f"fact-book-{book_id}",
                    book_node_id,
                    "book_summary",
                    f"{title} belongs to the {target_suffix.replace('_', ' ')} catalog.",
                    {
                        "confidence": "medium",
                        "category": target_suffix,
                    },
                )

        for category, relations in CATEGORY_RELATION_TARGETS.items():
            category_node_id = f"category:{category}"
            upsert_node(
                category_node_id,
                "category",
                category.replace("_", " ").title(),
                {"source": "catalog_anchor"},
            )
            for target_node_id, relation, weight in relations:
                target_type, target_suffix = target_node_id.split(":", 1)
                upsert_node(
                    target_node_id,
                    target_type,
                    target_suffix.replace("_", " ").title(),
                    {"source": "category_anchor"},
                )
                add_edge(
                    category_node_id,
                    target_node_id,
                    relation,
                    weight,
                    {"source": "catalog_anchor"},
                )

        payload = {
            "metadata": {
                "row_count": row_count,
                "book_count": len(books),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "fact_count": len(facts),
            },
            "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: (item["source"], item["target"], item["relation"])),
            "facts": sorted(facts, key=lambda item: (item["node_id"], item["id"])),
        }
        return payload

    @classmethod
    def write_export_artifacts(cls, output_dir, payload):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("nodes.json", "edges.json", "facts.json"):
            key = filename.replace(".json", "")
            (output_dir / filename).write_text(
                json.dumps(payload.get(key, []), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return {
            "nodes_path": output_dir / "nodes.json",
            "edges_path": output_dir / "edges.json",
            "facts_path": output_dir / "facts.json",
        }

    def neighbors(self, node_id):
        adjacency = self.adjacency.get(node_id, {"outgoing": [], "incoming": []})
        neighbor_ids = []
        for edge in adjacency["outgoing"]:
            if edge.target in self.nodes:
                neighbor_ids.append(edge.target)
        for edge in adjacency["incoming"]:
            if edge.source in self.nodes:
                neighbor_ids.append(edge.source)
        return sorted(set(neighbor_ids))

    def facts_for_node(self, node_id):
        return [fact for fact in self.facts if fact.node_id == node_id]

    def edges_for_node(self, node_id):
        adjacency = self.adjacency.get(node_id, {"outgoing": [], "incoming": []})
        return {
            "outgoing": list(adjacency["outgoing"]),
            "incoming": list(adjacency["incoming"]),
        }


class Neo4jGraphService:
    NODE_SYNC_QUERY = """
// graph nodes
UNWIND $nodes AS node
MERGE (n:GraphNode {id: node.id})
SET n.type = node.type,
    n.label = node.label,
    n.metadata_json = node.metadata_json
RETURN count(n) AS node_count
"""

    EDGE_SYNC_QUERY = """
// graph edges
UNWIND $edges AS edge
MATCH (source:GraphNode {id: edge.source})
MATCH (target:GraphNode {id: edge.target})
MERGE (source)-[r:RELATED_TO {relation: edge.relation}]->(target)
SET r.weight = edge.weight,
    r.metadata_json = edge.metadata_json
RETURN count(r) AS edge_count
"""

    FACT_SYNC_QUERY = """
// graph facts
UNWIND $facts AS fact
MATCH (node:GraphNode {id: fact.node_id})
MERGE (f:GraphFact {id: fact.id})
SET f.relation = fact.relation,
    f.statement = fact.statement,
    f.metadata_json = fact.metadata_json
MERGE (f)-[:DESCRIBES]->(node)
RETURN count(f) AS fact_count
"""

    NODE_FETCH_QUERY = """
// graph nodes
MATCH (n:GraphNode)
RETURN n.id AS id, n.type AS type, n.label AS label, {} AS metadata
ORDER BY n.id
"""

    EDGE_FETCH_QUERY = """
// graph edges
MATCH (source:GraphNode)-[r:RELATED_TO]->(target:GraphNode)
RETURN source.id AS source,
       target.id AS target,
       r.relation AS relation,
       coalesce(r.weight, 1.0) AS weight,
       {} AS metadata
ORDER BY source, target, relation
"""

    FACT_FETCH_QUERY = """
// graph facts
MATCH (f:GraphFact)-[:DESCRIBES]->(node:GraphNode)
RETURN f.id AS id,
       node.id AS node_id,
       f.relation AS relation,
       f.statement AS statement,
       {} AS metadata
ORDER BY node_id, id
"""

    IMPORT_CYPHER = "\n".join(
        [
            NODE_SYNC_QUERY.strip(),
            "",
            EDGE_SYNC_QUERY.strip(),
            "",
            FACT_SYNC_QUERY.strip(),
            "",
        ]
    )

    def __init__(self, uri=None, username=None, password=None, database=None, driver=None):
        self.uri = uri or None
        self.username = username or None
        self.password = password or None
        self.database = database or "neo4j"
        self._driver = driver

    @classmethod
    def from_env(cls, driver=None):
        return cls(
            uri=os.getenv("NEO4J_URI", "").strip() or None,
            username=os.getenv("NEO4J_USER", "").strip() or None,
            password=os.getenv("NEO4J_PASSWORD", "").strip() or None,
            database=os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
            driver=driver,
        )

    @property
    def is_configured(self):
        return bool(self.uri and self.username and self.password)

    @property
    def is_available(self):
        return self._driver is not None or self.is_configured

    def _create_driver(self):
        if self._driver is not None:
            return self._driver
        if not self.is_configured:
            return None
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("neo4j Python driver is required for Neo4j sync/query support.") from exc

        self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        return self._driver

    def export_graph_data(self, rows, books):
        return GraphKnowledgeBase.build_export_payload(rows, books)

    def write_export_artifacts(self, output_dir, rows=None, books=None, payload=None):
        payload = payload or self.export_graph_data(rows or [], books or [])
        return GraphKnowledgeBase.write_export_artifacts(output_dir, payload)

    @classmethod
    def build_import_cypher(cls):
        return cls.IMPORT_CYPHER

    def sync_graph_data(self, payload):
        driver = self._create_driver()
        if driver is None:
            return {"synced": False, "reason": "Neo4j connection is not configured."}

        def _serialize_metadata(items):
            serialized = []
            for item in list(items):
                record = dict(item)
                metadata = record.pop("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                record["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                serialized.append(record)
            return serialized

        nodes = _serialize_metadata(payload.get("nodes", []))
        edges = _serialize_metadata(payload.get("edges", []))
        facts = _serialize_metadata(payload.get("facts", []))

        def _first_count(result, key):
            if result is None:
                return 0

            record = None
            if hasattr(result, "single"):
                record = result.single()
            else:
                try:
                    record = list(result)[0]
                except Exception:
                    return 0

            if record is None:
                return 0
            if isinstance(record, dict):
                return int(record.get(key, 0) or 0)
            try:
                return int(record[key])  # pragma: no cover - neo4j Record path
            except Exception:
                try:
                    return int(record.data().get(key, 0) or 0)  # pragma: no cover - neo4j Record path
                except Exception:
                    return 0

        with driver.session(database=self.database) as session:
            try:
                tx = session.begin_transaction()
            except Exception as exc:
                raise RuntimeError("Neo4j transaction could not be started.") from exc

            try:
                tx.run("MATCH (n) WHERE n:GraphNode OR n:GraphFact DETACH DELETE n")
                node_result = tx.run(self.NODE_SYNC_QUERY, nodes=nodes)
                edge_result = tx.run(self.EDGE_SYNC_QUERY, edges=edges)
                fact_result = tx.run(self.FACT_SYNC_QUERY, facts=facts)
                counts = {
                    "node_count": _first_count(node_result, "node_count"),
                    "edge_count": _first_count(edge_result, "edge_count"),
                    "fact_count": _first_count(fact_result, "fact_count"),
                }
                tx.commit()
            except Exception:
                try:
                    tx.rollback()
                except Exception:
                    pass
                raise

        return {
            "synced": True,
            **counts,
        }

    def query_graph_data(self):
        driver = self._create_driver()
        if driver is None:
            return {"nodes": [], "edges": [], "facts": [], "metadata": {"synced": False}}

        with driver.session(database=self.database) as session:
            node_records = [dict(record) for record in session.run(self.NODE_FETCH_QUERY)]
            edge_records = [dict(record) for record in session.run(self.EDGE_FETCH_QUERY)]
            fact_records = [dict(record) for record in session.run(self.FACT_FETCH_QUERY)]

        graph = GraphKnowledgeBase.from_payload(
            {
                "nodes": node_records,
                "edges": edge_records,
                "facts": fact_records,
            }
        )
        return {
            "nodes": [dict(node.__dict__) for node in graph.nodes.values()],
            "edges": [dict(edge.__dict__) for edge in graph.edges],
            "facts": [dict(fact.__dict__) for fact in graph.facts],
            "metadata": {
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "fact_count": len(graph.facts),
            },
        }
