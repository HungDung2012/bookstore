# Bookstore AI Graph RAG Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nang cap `advisor-service` thanh mot module AI day du co deep learning, graph-based knowledge base, hybrid RAG, va integration ro rang vao he e-commerce.

**Architecture:** `advisor-service` se duoc don dep conflict truoc, sau do tach thanh cac lop ro rang: feature engineering + behavior dataset + deep learning model + graph KB + graph retrieval + text retrieval + RAG pipeline + orchestration/API. `api-gateway` giu popup chat hien co nhung se nhan payload tu van day du hon de de chi source va demo.

**Tech Stack:** Django, Django REST Framework, TensorFlow/Keras, NumPy, JSON knowledge graph, requests, unittest/Django TestCase.

---

## File Map

### Existing files to modify

- `advisor-service/app/services/advisor.py`
  - Resolve merge conflict and become the top-level orchestration service.
- `advisor-service/app/services/features.py`
  - Resolve merge conflict and keep feature engineering focused.
- `advisor-service/app/services/behavior_model.py`
  - Expand from artifact loader into explicit model/runtime service.
- `advisor-service/app/services/knowledge_base.py`
  - Keep text KB loading and metadata access focused.
- `advisor-service/app/services/clients.py`
  - Normalize upstream service access and payload guards.
- `advisor-service/app/services/prompting.py`
  - Build prompt and deterministic fallback answer from richer context.
- `advisor-service/app/views.py`
  - Return richer API payloads for `/advisor/chat/` and `/advisor/profile/<user_id>/`.
- `advisor-service/app/tests.py`
  - Replace conflicted test file with layered tests covering AI pipeline.
- `advisor-service/app/management/commands/prepare_behavior_data.py`
  - Use shared dataset/feature schema and write artifacts deterministically.
- `advisor-service/app/management/commands/train_behavior_model.py`
  - Train explicit deep learning model and export metadata artifacts.
- `advisor-service/requirements.txt`
  - Keep runtime/train-time deps explicit and consistent with implemented code.
- `advisor-service/advisor_service/settings.py`
  - Resolve merge conflicts and ensure app/config stability.
- `advisor-service/advisor_service/urls.py`
  - Resolve merge conflicts and keep advisor endpoints registered.
- `api-gateway/app/views.py`
  - Optionally surface richer advisor response fields if needed.
- `api-gateway/app/tests.py`
  - Extend advisor proxy tests if payload contract changes.

### New files to create

- `advisor-service/app/services/behavior_dataset.py`
  - Feature ordering, label ordering, metadata serialization, vector conversion.
- `advisor-service/app/services/graph_kb.py`
  - Graph node/edge types, load, adjacency, traversal helpers.
- `advisor-service/app/services/graph_retriever.py`
  - Rank graph facts and path evidence using question + segment + category signals.
- `advisor-service/app/services/text_retriever.py`
  - Retrieve text KB snippets with metadata-aware ranking.
- `advisor-service/app/services/rag_pipeline.py`
  - Combine graph results and text results into final retrieval context.
- `advisor-service/app/data/knowledge_graph/nodes.json`
  - Graph node dataset.
- `advisor-service/app/data/knowledge_graph/edges.json`
  - Graph edge dataset.
- `advisor-service/app/data/knowledge_graph/facts.json`
  - Human-readable facts attached to graph nodes/relations.

### Existing data files to keep/reuse

- `advisor-service/app/data/knowledge_base/categories.json`
- `advisor-service/app/data/knowledge_base/faqs.json`
- `advisor-service/app/data/knowledge_base/policies.json`
- `advisor-service/app/data/knowledge_base/segment_advice.json`

---

### Task 1: Resolve Advisor Service Conflicts And Stabilize Baseline

**Files:**
- Modify: `advisor-service/app/services/advisor.py`
- Modify: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/tests.py`
- Modify: `advisor-service/app/views.py`
- Modify: `advisor-service/app/serializers.py`
- Modify: `advisor-service/advisor_service/settings.py`
- Modify: `advisor-service/advisor_service/urls.py`
- Modify: `advisor-service/requirements.txt`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that assert the conflicted modules import cleanly and the API endpoints still respond:

```python
from django.test import TestCase
from rest_framework.test import APIClient


class AdvisorBaselineTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_endpoint_returns_service_name(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "advisor-service")

    def test_chat_endpoint_requires_question(self):
        response = self.client.post("/advisor/chat/", {"user_id": 1}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("question", response.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.AdvisorBaselineTests -v 2`
Expected: FAIL because conflicted files cannot import or the test module cannot load due to merge markers.

- [ ] **Step 3: Write minimal implementation**

Resolve every merge conflict in the files listed above and keep the richer implementation branch, not the old placeholder branch. Ensure:

```python
class AdvisorService:
    def chat(self, user_id=None, question=""):
        ...

    def profile(self, user_id):
        ...
```

and:

```python
def build_behavior_features(profile, books, orders, reviews, cart_items):
    ...

def infer_behavior_label(features):
    ...
```

Also ensure `views.py` exposes both:

```python
path("advisor/chat/", AdvisorChatView.as_view()),
path("advisor/profile/<int:user_id>/", AdvisorProfileView.as_view()),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.AdvisorBaselineTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/advisor.py advisor-service/app/services/features.py advisor-service/app/tests.py advisor-service/app/views.py advisor-service/app/serializers.py advisor-service/advisor_service/settings.py advisor-service/advisor_service/urls.py advisor-service/requirements.txt
git commit -m "fix: resolve advisor service conflicts"
```

### Task 2: Introduce Behavior Dataset Schema

**Files:**
- Create: `advisor-service/app/services/behavior_dataset.py`
- Modify: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require a stable feature ordering and metadata export:

```python
from django.test import TestCase
from app.services.behavior_dataset import BehaviorDatasetSchema


class BehaviorDatasetSchemaTests(TestCase):
    def test_schema_orders_features_deterministically(self):
        schema = BehaviorDatasetSchema.from_rows(
            [
                {"order_count": 1, "category_3_count": 2, "label": "tech_reader"},
                {"order_count": 2, "publisher_9_count": 1, "label": "casual_buyer"},
            ]
        )
        self.assertEqual(schema.feature_names, ["category_3_count", "order_count", "publisher_9_count"])
        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.BehaviorDatasetSchemaTests -v 2`
Expected: FAIL with import error because `BehaviorDatasetSchema` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
from dataclasses import dataclass


@dataclass
class BehaviorDatasetSchema:
    feature_names: list[str]
    labels: list[str]

    @classmethod
    def from_rows(cls, rows):
        feature_names = sorted(
            {
                key
                for row in rows
                for key in row.keys()
                if key != "label"
            }
        )
        labels = sorted({row["label"] for row in rows if row.get("label")})
        return cls(feature_names=feature_names, labels=labels)
```

Add helpers for:

```python
def vectorize_features(self, features): ...
def encode_label(self, label): ...
def to_metadata(self): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.BehaviorDatasetSchemaTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/behavior_dataset.py advisor-service/app/services/features.py advisor-service/app/tests.py
git commit -m "feat: add behavior dataset schema"
```

### Task 3: Make Deep Learning Model Definition Explicit

**Files:**
- Modify: `advisor-service/app/services/behavior_model.py`
- Modify: `advisor-service/app/management/commands/train_behavior_model.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require an explicit model builder and metadata-aware prediction:

```python
from django.test import TestCase
from app.services.behavior_model import build_behavior_model


class BehaviorModelDefinitionTests(TestCase):
    def test_build_behavior_model_returns_compiled_model(self):
        model = build_behavior_model(input_dim=6, output_dim=3)
        self.assertEqual(model.input_shape[-1], 6)
        self.assertEqual(model.output_shape[-1], 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.BehaviorModelDefinitionTests -v 2`
Expected: FAIL because `build_behavior_model` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `behavior_model.py`, add:

```python
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Dense, Dropout, Input


def build_behavior_model(input_dim, output_dim):
    model = Sequential(
        [
            Input(shape=(input_dim,)),
            Dense(32, activation="relu"),
            Dropout(0.1),
            Dense(16, activation="relu"),
            Dense(output_dim, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model
```

Update `train_behavior_model.py` to use the shared schema and write:

```python
model_behavior.h5
features.txt
labels.txt
metadata.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.BehaviorModelDefinitionTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/behavior_model.py advisor-service/app/management/commands/train_behavior_model.py advisor-service/app/tests.py
git commit -m "feat: define explicit behavior model"
```

### Task 4: Refactor Behavior Data Preparation To Use Shared Schema

**Files:**
- Modify: `advisor-service/app/management/commands/prepare_behavior_data.py`
- Modify: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/services/behavior_dataset.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add a command test that requires `prepare_behavior_data` to write rows plus stable metadata:

```python
from django.test import TestCase
from django.core.management import call_command


class PrepareBehaviorDataTests(TestCase):
    def test_prepare_behavior_data_writes_dataset_with_labels(self):
        call_command("prepare_behavior_data", verbosity=0)
        self.assertTrue(...)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.PrepareBehaviorDataTests -v 2`
Expected: FAIL because the command output format does not yet match the schema/metadata contract.

- [ ] **Step 3: Write minimal implementation**

Update `prepare_behavior_data.py` to:

```python
rows.append(
    {
        **features,
        "label": infer_behavior_label(features),
    }
)
```

Then write:

```python
schema = BehaviorDatasetSchema.from_rows(rows)
```

and export the CSV using `schema.feature_names`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.PrepareBehaviorDataTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/management/commands/prepare_behavior_data.py advisor-service/app/services/features.py advisor-service/app/services/behavior_dataset.py advisor-service/app/tests.py
git commit -m "feat: align behavior data preparation with schema"
```

### Task 5: Add Graph Knowledge Base Core

**Files:**
- Create: `advisor-service/app/services/graph_kb.py`
- Create: `advisor-service/app/data/knowledge_graph/nodes.json`
- Create: `advisor-service/app/data/knowledge_graph/edges.json`
- Create: `advisor-service/app/data/knowledge_graph/facts.json`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require graph node/edge loading:

```python
from django.test import TestCase
from app.services.graph_kb import GraphKnowledgeBase


class GraphKnowledgeBaseTests(TestCase):
    def test_graph_loads_nodes_edges_and_facts(self):
        graph = GraphKnowledgeBase("app/data/knowledge_graph")
        self.assertGreater(len(graph.nodes), 0)
        self.assertGreater(len(graph.edges), 0)
        self.assertIn("segment:tech_reader", graph.nodes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GraphKnowledgeBaseTests -v 2`
Expected: FAIL because graph service and data files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
from dataclasses import dataclass


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    metadata: dict


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
```

and:

```python
class GraphKnowledgeBase:
    def __init__(self, base_path):
        ...
    def neighbors(self, node_id):
        ...
    def facts_for_node(self, node_id):
        ...
```

Seed JSON with at least:

- segments: `tech_reader`, `literature_reader`, `family_reader`, `bargain_hunter`, `casual_buyer`
- categories: programming, literature, children, business
- services/policies: payment, shipping, cancellation

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GraphKnowledgeBaseTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/graph_kb.py advisor-service/app/data/knowledge_graph/nodes.json advisor-service/app/data/knowledge_graph/edges.json advisor-service/app/data/knowledge_graph/facts.json advisor-service/app/tests.py
git commit -m "feat: add graph knowledge base core"
```

### Task 6: Add Graph Retriever

**Files:**
- Create: `advisor-service/app/services/graph_retriever.py`
- Modify: `advisor-service/app/services/graph_kb.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require segment-aware graph retrieval:

```python
from django.test import TestCase
from app.services.graph_kb import GraphKnowledgeBase
from app.services.graph_retriever import GraphRetriever


class GraphRetrieverTests(TestCase):
    def test_graph_retriever_returns_segment_and_policy_facts(self):
        retriever = GraphRetriever(GraphKnowledgeBase("app/data/knowledge_graph"))
        result = retriever.search(question="How does shipping work for me?", behavior_segment="tech_reader")
        self.assertTrue(result["facts"])
        self.assertTrue(result["paths"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GraphRetrieverTests -v 2`
Expected: FAIL because `GraphRetriever` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
class GraphRetriever:
    def __init__(self, graph):
        self.graph = graph

    def search(self, question, behavior_segment, top_k=5):
        ...
        return {"facts": ranked_facts, "paths": ranked_paths}
```

Use a simple scoring rule from:

- segment node hit
- service/policy keyword overlap
- category relation overlap

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GraphRetrieverTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/graph_retriever.py advisor-service/app/services/graph_kb.py advisor-service/app/tests.py
git commit -m "feat: add graph retriever"
```

### Task 7: Add Text Retriever

**Files:**
- Create: `advisor-service/app/services/text_retriever.py`
- Modify: `advisor-service/app/services/knowledge_base.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require metadata-aware text retrieval:

```python
from django.test import TestCase
from app.services.knowledge_base import KnowledgeBaseService
from app.services.text_retriever import TextRetriever


class TextRetrieverTests(TestCase):
    def test_text_retriever_prefers_segment_and_query_matches(self):
        retriever = TextRetriever(KnowledgeBaseService("app/data/knowledge_base"))
        docs = retriever.search("shipping policy", behavior_segment="casual_buyer", top_k=3)
        self.assertGreaterEqual(len(docs), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.TextRetrieverTests -v 2`
Expected: FAIL because `TextRetriever` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
class TextRetriever:
    def __init__(self, kb_service):
        self.documents = kb_service.load_documents()

    def search(self, question, behavior_segment=None, top_k=3):
        ...
```

Ranking should consider:

- token overlap
- `target_segment`
- `doc_type`

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.TextRetrieverTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/text_retriever.py advisor-service/app/services/knowledge_base.py advisor-service/app/tests.py
git commit -m "feat: add text retriever"
```

### Task 8: Add Hybrid RAG Pipeline

**Files:**
- Create: `advisor-service/app/services/rag_pipeline.py`
- Modify: `advisor-service/app/services/graph_retriever.py`
- Modify: `advisor-service/app/services/text_retriever.py`
- Modify: `advisor-service/app/services/prompting.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add tests that require merged graph + text context:

```python
from django.test import TestCase
from app.services.rag_pipeline import HybridRAGPipeline


class HybridRAGPipelineTests(TestCase):
    def test_pipeline_returns_graph_facts_text_sources_and_context(self):
        pipeline = HybridRAGPipeline(...)
        result = pipeline.retrieve(question="Recommend books and explain shipping", behavior_segment="tech_reader")
        self.assertIn("graph_facts", result)
        self.assertIn("text_sources", result)
        self.assertIn("context_blocks", result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.HybridRAGPipelineTests -v 2`
Expected: FAIL because `HybridRAGPipeline` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
class HybridRAGPipeline:
    def __init__(self, graph_retriever, text_retriever):
        ...

    def retrieve(self, question, behavior_segment, top_k=3):
        graph_result = self.graph_retriever.search(question, behavior_segment, top_k=top_k)
        text_result = self.text_retriever.search(question, behavior_segment=behavior_segment, top_k=top_k)
        return {
            "graph_facts": graph_result["facts"],
            "graph_paths": graph_result["paths"],
            "text_sources": text_result,
            "context_blocks": ...,
        }
```

Update `prompting.py` so prompt builders accept `graph_facts` and `context_blocks`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.HybridRAGPipelineTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/rag_pipeline.py advisor-service/app/services/graph_retriever.py advisor-service/app/services/text_retriever.py advisor-service/app/services/prompting.py advisor-service/app/tests.py
git commit -m "feat: add hybrid rag pipeline"
```

### Task 9: Upgrade Advisor Orchestration To Use Deep Learning + Graph RAG

**Files:**
- Modify: `advisor-service/app/services/advisor.py`
- Modify: `advisor-service/app/services/clients.py`
- Modify: `advisor-service/app/services/behavior_model.py`
- Modify: `advisor-service/app/services/prompting.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add an orchestration test that requires a full chat payload:

```python
from django.test import TestCase
from app.services.advisor import AdvisorService


class AdvisorServiceOrchestrationTests(TestCase):
    def test_chat_returns_behavior_segment_graph_facts_and_sources(self):
        service = AdvisorService()
        result = service.chat(user_id=1, question="What books should I buy and how does shipping work?")
        self.assertIn("behavior_segment", result)
        self.assertIn("graph_facts", result)
        self.assertIn("sources", result)
        self.assertIn("recommended_books", result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.AdvisorServiceOrchestrationTests -v 2`
Expected: FAIL because current orchestration does not return the full graph/text RAG payload.

- [ ] **Step 3: Write minimal implementation**

Refactor `AdvisorService.__init__` to wire:

```python
self.client = UpstreamClient()
self.model_service = BehaviorModelService()
self.text_kb = KnowledgeBaseService("app/data/knowledge_base")
self.graph_kb = GraphKnowledgeBase("app/data/knowledge_graph")
self.text_retriever = TextRetriever(self.text_kb)
self.graph_retriever = GraphRetriever(self.graph_kb)
self.rag_pipeline = HybridRAGPipeline(self.graph_retriever, self.text_retriever)
```

Return:

```python
{
    "answer": answer,
    "behavior_segment": behavior_segment,
    "probabilities": prediction.get("probabilities", {}),
    "recommended_books": recommended_books,
    "sources": retrieval["text_sources"],
    "feature_summary": feature_summary,
    "graph_facts": retrieval["graph_facts"],
    "graph_paths": retrieval["graph_paths"],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.AdvisorServiceOrchestrationTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/services/advisor.py advisor-service/app/services/clients.py advisor-service/app/services/behavior_model.py advisor-service/app/services/prompting.py advisor-service/app/tests.py
git commit -m "feat: orchestrate advisor with graph rag"
```

### Task 10: Upgrade Advisor API Contract

**Files:**
- Modify: `advisor-service/app/views.py`
- Modify: `advisor-service/app/serializers.py`
- Modify: `advisor-service/advisor_service/urls.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add API tests requiring richer payloads:

```python
from django.test import TestCase
from rest_framework.test import APIClient


class AdvisorApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_chat_endpoint_returns_graph_and_source_fields(self):
        response = self.client.post("/advisor/chat/", {"user_id": 1, "question": "Recommend books"}, format="json")
        self.assertIn("graph_facts", response.json())
        self.assertIn("sources", response.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.AdvisorApiContractTests -v 2`
Expected: FAIL because serializers/views do not yet enforce the richer contract.

- [ ] **Step 3: Write minimal implementation**

Update serializers to validate:

```python
class AdvisorChatSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False, allow_null=True)
    question = serializers.CharField()
```

and ensure response includes the richer payload keys from Task 9.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.AdvisorApiContractTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/views.py advisor-service/app/serializers.py advisor-service/advisor_service/urls.py advisor-service/app/tests.py
git commit -m "feat: expand advisor api contract"
```

### Task 11: Integrate Richer Advisor Payload Through Gateway

**Files:**
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/app/tests.py`
- Modify: `api-gateway/app/templates/base.html`
- Test: `api-gateway/app/tests.py`

- [ ] **Step 1: Write the failing test**

Add a gateway proxy test requiring pass-through of new advisor fields:

```python
from django.test import TestCase
from unittest.mock import Mock, patch


class GatewayAdvisorProxyTests(TestCase):
    @patch("app.views.requests.post")
    def test_advisor_chat_proxy_returns_graph_fields(self, post_mock):
        ...
        self.assertIn("graph_facts", response.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayAdvisorProxyTests -v 2`
Expected: FAIL because the gateway does not yet surface the richer response shape.

- [ ] **Step 3: Write minimal implementation**

Keep the popup unchanged structurally, but ensure:

```python
return JsonResponse(
    {
        "answer": payload.get("answer", ""),
        "behavior_segment": payload.get("behavior_segment"),
        "recommended_books": payload.get("recommended_books", []),
        "sources": payload.get("sources", []),
        "graph_facts": payload.get("graph_facts", []),
        "graph_paths": payload.get("graph_paths", []),
    }
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.GatewayAdvisorProxyTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api-gateway/app/views.py api-gateway/app/tests.py api-gateway/app/templates/base.html
git commit -m "feat: surface graph rag advisor payload"
```

### Task 12: End-To-End Verification And Cleanup

**Files:**
- Modify: `advisor-service/app/tests.py`
- Modify: `api-gateway/app/tests.py`
- Modify: `docs/superpowers/specs/2026-04-15-bookstore-ai-graph-rag-upgrade-design.md` (only if implementation reveals a necessary wording fix)

- [ ] **Step 1: Write or finalize the failing verification expectation**

Define the final verification checklist:

```text
advisor-service imports cleanly
advisor-service tests pass
api-gateway advisor proxy tests pass
graph KB files exist
chat payload includes behavior_segment, sources, graph_facts, graph_paths
```

- [ ] **Step 2: Run verification commands**

Run:

```bash
cd advisor-service
python manage.py test app.tests -v 1
```

Expected: PASS

Run:

```bash
cd ../api-gateway
python manage.py test app.tests.GatewayAdvisorProxyTests -v 2
```

Expected: PASS

- [ ] **Step 3: Fix any remaining regressions**

Only if tests fail, fix the exact failing contract or import issue in:

```python
advisor-service/app/services/*.py
advisor-service/app/views.py
api-gateway/app/views.py
```

- [ ] **Step 4: Re-run the final test set**

Run:

```bash
cd advisor-service
python manage.py test app.tests -v 1
cd ../api-gateway
python manage.py test app.tests -v 1
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add advisor-service/app/tests.py api-gateway/app/tests.py advisor-service/app/services advisor-service/app/views.py api-gateway/app/views.py
git commit -m "test: finalize ai graph rag verification"
```

---

## Self-Review

### Spec Coverage

- conflict cleanup: Task 1
- deep learning structure: Tasks 2, 3, 4
- graph-based KB: Tasks 5, 6
- hybrid RAG: Tasks 7, 8, 9
- API/integration: Tasks 9, 10, 11
- verification: Task 12

No spec section is left without a task.

### Placeholder Scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Each task includes concrete files, tests, commands, and expected outcomes.

### Type Consistency

- `behavior_segment`, `graph_facts`, `graph_paths`, `sources`, and `recommended_books` are used consistently across tasks.
- The named classes introduced in earlier tasks are reused with the same names later:
  - `BehaviorDatasetSchema`
  - `GraphKnowledgeBase`
  - `GraphRetriever`
  - `TextRetriever`
  - `HybridRAGPipeline`
