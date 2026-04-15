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
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_nodes(self):
        nodes = {}
        for item in self._read_json("nodes.json"):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            metadata = item.get("metadata") or {}
            nodes[item["id"]] = GraphNode(
                id=item["id"],
                type=str(item.get("type", "")).strip(),
                label=str(item.get("label", "")).strip(),
                metadata=metadata if isinstance(metadata, dict) else {},
            )
        return nodes

    def _load_edges(self):
        edges = []
        for item in self._read_json("edges.json"):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") or {}
            edges.append(
                GraphEdge(
                    source=str(item.get("source", "")).strip(),
                    target=str(item.get("target", "")).strip(),
                    relation=str(item.get("relation", "")).strip(),
                    weight=float(item.get("weight", 1.0) or 1.0),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return edges

    def _load_facts(self):
        facts = []
        for item in self._read_json("facts.json"):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            metadata = item.get("metadata") or {}
            facts.append(
                GraphFact(
                    id=item["id"],
                    node_id=str(item.get("node_id", "")).strip(),
                    relation=str(item.get("relation", "")).strip(),
                    statement=str(item.get("statement", "")).strip(),
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
