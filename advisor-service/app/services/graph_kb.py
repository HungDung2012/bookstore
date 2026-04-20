import json
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


class GraphKnowledgeBase:
    _APP_ROOT = Path(__file__).resolve().parents[2]

    def __init__(self, base_path):
        base_path = Path(base_path)
        self.base_path = base_path if base_path.is_absolute() else self._APP_ROOT / base_path

        self.nodes = self._load_nodes()
        self.edges = self._load_edges()
        self.facts = self._load_facts()
        self.adjacency = self._build_adjacency()

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

    def _load_nodes(self):
        nodes = {}
        for item in self._read_json("nodes.json"):
            if not isinstance(item, dict):
                raise ValueError("Node record must be a JSON object")
            node_id = self._require_nonblank_string(item, "id", "Node")
            if node_id in nodes:
                raise ValueError(f"Duplicate node id: {node_id}")
            metadata = item.get("metadata") or {}
            nodes[node_id] = GraphNode(
                id=node_id,
                type=str(item.get("type", "")).strip(),
                label=str(item.get("label", "")).strip(),
                metadata=metadata if isinstance(metadata, dict) else {},
            )
        return nodes

    def _load_edges(self):
        edges = []
        for item in self._read_json("edges.json"):
            if not isinstance(item, dict):
                raise ValueError("Edge record must be a JSON object")
            metadata = item.get("metadata") or {}
            source = self._require_nonblank_string(item, "source", "Edge")
            target = self._require_nonblank_string(item, "target", "Edge")
            relation = self._require_nonblank_string(item, "relation", "Edge")
            weight = item.get("weight", 1.0)
            if weight is None:
                weight = 1.0
            edges.append(
                GraphEdge(
                    source=source,
                    target=target,
                    relation=relation,
                    weight=float(weight),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )

        for edge in edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ValueError(
                    f"Edge endpoints must reference existing nodes: {edge.source} -> {edge.target}"
                )
        return edges

    def _load_facts(self):
        facts = []
        for item in self._read_json("facts.json"):
            if not isinstance(item, dict):
                raise ValueError("Fact record must be a JSON object")
            metadata = item.get("metadata") or {}
            fact_id = self._require_nonblank_string(item, "id", "Fact")
            node_id = self._require_nonblank_string(item, "node_id", "Fact")
            relation = self._require_nonblank_string(item, "relation", "Fact")
            statement = self._require_nonblank_string(item, "statement", "Fact")
            if node_id not in self.nodes:
                raise ValueError(f"Fact node_id must reference an existing node: {node_id}")
            facts.append(
                GraphFact(
                    id=fact_id,
                    node_id=node_id,
                    relation=relation,
                    statement=statement,
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return facts

    def _build_adjacency(self):
        adjacency = {
            node_id: {"outgoing": [], "incoming": []}
            for node_id in self.nodes
        }
        for edge in self.edges:
            adjacency.setdefault(edge.source, {"outgoing": [], "incoming": []})["outgoing"].append(edge)
            adjacency.setdefault(edge.target, {"outgoing": [], "incoming": []})["incoming"].append(edge)
        return adjacency

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
