# Bookstore AI Ecommerce Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a sequence-based AI advisor for the bookstore that generates a 500-user behavior dataset, trains and compares RNN/LSTM/biLSTM models, syncs a Neo4j knowledge graph, and surfaces graph-aware recommendations and chat in the e-commerce UI.

**Architecture:** Keep the existing `advisor-service` as the orchestration boundary, but replace flat behavior classification with sequence modeling and runtime sequence extraction. Persist both model artifacts and graph artifacts in the repo, query Neo4j at runtime for graph context, and expose richer advisor payloads to `api-gateway` for recommendation blocks and a custom bookstore chat panel.

**Tech Stack:** Django, Django REST Framework, TensorFlow/Keras, NumPy, pandas, scikit-learn, matplotlib, Neo4j Python driver, requests

---

## File Structure

### Create

- `advisor-service/app/data/training/data_user500.csv`
- `advisor-service/app/data/training/data_user500_sample20.csv`
- `advisor-service/app/data/training/data_user500_metadata.json`
- `advisor-service/app/management/commands/sync_behavior_graph.py`
- `advisor-service/app/data/knowledge_graph/import.cypher`
- `api-gateway/app/templates/partials/advisor_panel.html`

### Modify

- `advisor-service/requirements.txt`
- `advisor-service/app/services/behavior_dataset.py`
- `advisor-service/app/services/behavior_model.py`
- `advisor-service/app/services/features.py`
- `advisor-service/app/services/graph_kb.py`
- `advisor-service/app/services/graph_retriever.py`
- `advisor-service/app/services/rag_pipeline.py`
- `advisor-service/app/services/prompting.py`
- `advisor-service/app/services/advisor.py`
- `advisor-service/app/services/clients.py`
- `advisor-service/app/management/commands/prepare_behavior_data.py`
- `advisor-service/app/management/commands/train_behavior_model.py`
- `advisor-service/app/tests.py`
- `api-gateway/app/views.py`
- `api-gateway/app/templates/books.html`
- `api-gateway/app/templates/cart.html`
- `api-gateway/app/templates/base.html`

### Runtime Artifact Outputs

- `advisor-service/app/data/models/model_rnn.keras`
- `advisor-service/app/data/models/model_lstm.keras`
- `advisor-service/app/data/models/model_bilstm.keras`
- `advisor-service/app/data/models/model_best.keras`
- `advisor-service/app/data/models/model_comparison.json`
- `advisor-service/app/data/models/model_metadata.json`
- `advisor-service/app/data/models/plots/*.png`
- `advisor-service/app/data/knowledge_graph/nodes.json`
- `advisor-service/app/data/knowledge_graph/edges.json`
- `advisor-service/app/data/knowledge_graph/facts.json`

### Test Surface

- `advisor-service/app/tests.py`
- targeted Django test runs in `advisor-service`

### Task 1: Build the sequence dataset generator

**Files:**
- Modify: `advisor-service/app/services/behavior_dataset.py`
- Modify: `advisor-service/app/management/commands/prepare_behavior_data.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing dataset tests**

```python
class SequenceDatasetTests(TestCase):
    def test_generate_user500_dataset_has_expected_shape(self):
        from app.management.commands.prepare_behavior_data import generate_behavior_dataset_rows

        rows = generate_behavior_dataset_rows(user_count=500, seed=42)

        self.assertEqual(len(rows), 500)
        self.assertIn("step_1_behavior", rows[0])
        self.assertIn("step_8_duration", rows[0])
        self.assertIn("label", rows[0])

    def test_schema_encodes_sequence_columns_and_sample_export(self):
        from app.services.behavior_dataset import BehaviorSequenceSchema

        schema = BehaviorSequenceSchema.default()
        self.assertEqual(schema.sequence_length, 8)
        self.assertIn("step_1_behavior", schema.csv_columns)
        self.assertIn("step_8_price_band", schema.csv_columns)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.SequenceDatasetTests -v 2`
Expected: FAIL because `BehaviorSequenceSchema` and `generate_behavior_dataset_rows` do not exist yet.

- [ ] **Step 3: Write minimal dataset/schema implementation**

```python
@dataclass(frozen=True)
class BehaviorSequenceSchema:
    sequence_length: int
    behavior_vocab: list[str]

    @classmethod
    def default(cls):
        return cls(sequence_length=8, behavior_vocab=BEHAVIOR_VOCAB)

    @property
    def csv_columns(self):
        columns = ["user_id", "age_group", "favorite_category", "price_sensitivity", "membership_tier"]
        for step in range(1, self.sequence_length + 1):
            columns.extend(
                [
                    f"step_{step}_behavior",
                    f"step_{step}_category",
                    f"step_{step}_price_band",
                    f"step_{step}_duration",
                ]
            )
        columns.append("label")
        return columns
```

```python
def generate_behavior_dataset_rows(user_count=500, seed=42):
    random.seed(seed)
    rows = []
    for user_id in range(1, user_count + 1):
        rows.append(build_synthetic_user_row(user_id=user_id))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test app.tests.SequenceDatasetTests -v 2`
Expected: PASS

- [ ] **Step 5: Expand command to write CSV, sample20, and metadata**

```python
rows = generate_behavior_dataset_rows(user_count=500, seed=options["seed"])
write_dataset_csv(DATASET_PATH, rows, schema)
write_dataset_csv(SAMPLE_PATH, rows[:20], schema)
METADATA_PATH.write_text(json.dumps(build_dataset_metadata(rows, schema), indent=2), encoding="utf-8")
```

- [ ] **Step 6: Run command to verify artifacts are created**

Run: `python manage.py prepare_behavior_data --seed 42`
Expected: command exits 0 and creates `data_user500.csv`, `data_user500_sample20.csv`, and metadata JSON.

- [ ] **Step 7: Commit**

```bash
git add advisor-service/app/services/behavior_dataset.py advisor-service/app/management/commands/prepare_behavior_data.py advisor-service/app/tests.py
git commit -m "feat: generate sequence behavior dataset"
```

### Task 2: Train and compare RNN, LSTM, and biLSTM

**Files:**
- Modify: `advisor-service/app/services/behavior_model.py`
- Modify: `advisor-service/app/management/commands/train_behavior_model.py`
- Modify: `advisor-service/app/tests.py`
- Test: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing model-selection tests**

```python
class SequenceModelSelectionTests(TestCase):
    def test_select_best_model_prefers_highest_macro_f1(self):
        from app.management.commands.train_behavior_model import select_best_model_result

        best = select_best_model_result(
            [
                {"model_name": "rnn", "f1_macro": 0.74, "accuracy": 0.80},
                {"model_name": "lstm", "f1_macro": 0.79, "accuracy": 0.78},
                {"model_name": "bilstm", "f1_macro": 0.79, "accuracy": 0.81},
            ]
        )

        self.assertEqual(best["model_name"], "bilstm")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.SequenceModelSelectionTests -v 2`
Expected: FAIL because selection helpers and sequence model service do not exist yet.

- [ ] **Step 3: Implement sequence encoding and three Keras builders**

```python
def build_rnn_model(input_shape, output_dim):
    model = Sequential(
        [
            Input(shape=input_shape),
            SimpleRNN(64, activation="tanh"),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(output_dim, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model
```

```python
def build_lstm_model(input_shape, output_dim):
    model = Sequential(
        [
            Input(shape=input_shape),
            LSTM(64),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(output_dim, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model
```

```python
def build_bilstm_model(input_shape, output_dim):
    model = Sequential(
        [
            Input(shape=input_shape),
            Bidirectional(LSTM(64)),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(output_dim, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model
```

- [ ] **Step 4: Run test to verify builder/selection logic passes**

Run: `python manage.py test app.tests.SequenceModelSelectionTests -v 2`
Expected: PASS

- [ ] **Step 5: Implement training command outputs and runtime `model_best` loading**

```python
results = [
    train_single_model("rnn", build_rnn_model, X_train, y_train, X_test, y_test),
    train_single_model("lstm", build_lstm_model, X_train, y_train, X_test, y_test),
    train_single_model("bilstm", build_bilstm_model, X_train, y_train, X_test, y_test),
]
best = select_best_model_result(results)
copyfile(best["model_path"], OUTPUT_DIR / "model_best.keras")
```

```python
return {
    "behavior_segment": labels[best_index],
    "probabilities": {label: float(prob) for label, prob in zip(labels, probabilities)},
    "model_name": metadata.get("best_model_name", "model_best"),
    "sequence_summary": summarize_sequence(encoded_sequence, labels[best_index]),
}
```

- [ ] **Step 6: Run training command for fresh verification**

Run: `python manage.py train_behavior_model`
Expected: exit 0, three `.keras` files, one `model_best.keras`, metrics JSON, and plots under `app/data/models/plots/`.

- [ ] **Step 7: Commit**

```bash
git add advisor-service/app/services/behavior_model.py advisor-service/app/management/commands/train_behavior_model.py advisor-service/app/tests.py advisor-service/app/data/models
git commit -m "feat: train and compare sequence behavior models"
```

### Task 3: Add Neo4j graph export and runtime querying

**Files:**
- Modify: `advisor-service/app/services/graph_kb.py`
- Modify: `advisor-service/app/services/graph_retriever.py`
- Create: `advisor-service/app/management/commands/sync_behavior_graph.py`
- Create: `advisor-service/app/data/knowledge_graph/import.cypher`
- Modify: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing graph integration tests**

```python
class Neo4jGraphTests(TestCase):
    def test_build_graph_export_contains_users_segments_and_books(self):
        from app.services.graph_kb import build_behavior_graph_export

        export = build_behavior_graph_export(
            dataset_rows=[{"user_id": 1, "label": "loyal_reader", "favorite_category": "fiction"}],
            books=[{"id": 9, "title": "Book", "category": 5, "author": "A"}],
        )

        self.assertTrue(export["nodes"])
        self.assertTrue(export["edges"])

    def test_query_adapter_returns_graph_paths(self):
        from app.services.graph_kb import Neo4jGraphService

        service = Neo4jGraphService(uri="bolt://localhost:7687", username="neo4j", password="test")
        self.assertTrue(hasattr(service, "recommend_books_for_segment"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.Neo4jGraphTests -v 2`
Expected: FAIL because graph export builder and Neo4j service are missing.

- [ ] **Step 3: Implement graph export classes and Neo4j service skeleton**

```python
class Neo4jGraphService:
    def __init__(self, uri=None, username=None, password=None, database=None, driver=None):
        self.driver = driver or GraphDatabase.driver(uri, auth=(username, password))
        self.database = database or "neo4j"

    def recommend_books_for_segment(self, segment, limit=5):
        query = """
        MATCH (:Segment {name: $segment})-[:LIKES]->(book:Book)
        RETURN book.id AS id, book.title AS title
        LIMIT $limit
        """
        return self._run_read(query, {"segment": segment, "limit": limit})
```

```python
def build_behavior_graph_export(dataset_rows, books):
    nodes = []
    edges = []
    facts = []
    # create User, Segment, Category, Book nodes and relations
    return {"nodes": nodes, "edges": edges, "facts": facts}
```

- [ ] **Step 4: Run test to verify graph code passes**

Run: `python manage.py test app.tests.Neo4jGraphTests -v 2`
Expected: PASS

- [ ] **Step 5: Implement sync command and Cypher import script**

```python
class Command(BaseCommand):
    help = "Sync behavior graph artifacts into Neo4j."

    def handle(self, *args, **options):
        export = build_behavior_graph_export(dataset_rows=load_dataset_rows(), books=load_books())
        write_graph_artifacts(export)
        Neo4jGraphService.from_env().sync_export(export)
        self.stdout.write(self.style.SUCCESS("Behavior graph synced to Neo4j"))
```

- [ ] **Step 6: Run graph sync verification**

Run: `python manage.py sync_behavior_graph`
Expected: exit 0, refreshed `nodes.json`/`edges.json`/`facts.json`, and Neo4j receives graph data.

- [ ] **Step 7: Commit**

```bash
git add advisor-service/app/services/graph_kb.py advisor-service/app/services/graph_retriever.py advisor-service/app/management/commands/sync_behavior_graph.py advisor-service/app/data/knowledge_graph advisor-service/app/tests.py
git commit -m "feat: add neo4j behavior graph sync"
```

### Task 4: Upgrade advisor orchestration to sequence + graph-aware RAG

**Files:**
- Modify: `advisor-service/app/services/features.py`
- Modify: `advisor-service/app/services/clients.py`
- Modify: `advisor-service/app/services/rag_pipeline.py`
- Modify: `advisor-service/app/services/prompting.py`
- Modify: `advisor-service/app/services/advisor.py`
- Modify: `advisor-service/app/views.py`
- Modify: `advisor-service/app/tests.py`

- [ ] **Step 1: Write the failing orchestration tests**

```python
class AdvisorSequenceRagTests(TestCase):
    def test_chat_returns_model_name_and_sequence_summary(self):
        service = AdvisorService()
        with patch.object(service, "_collect_behavior_inputs", return_value=([], {"id": 1}, [], [], [])):
            with patch.object(service, "_predict_behavior", return_value=(
                {"sequence": []},
                {"behavior_segment": "loyal_reader", "probabilities": {"loyal_reader": 0.9}, "model_name": "bilstm", "sequence_summary": "8 steps"}
            )):
                result = service.chat(user_id=1, question="goi y sach")
        self.assertEqual(result["model_name"], "bilstm")
        self.assertIn("sequence_summary", result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.AdvisorSequenceRagTests -v 2`
Expected: FAIL because payload shape and runtime sequence flow are not implemented yet.

- [ ] **Step 3: Implement runtime sequence extraction and graph-first retrieval**

```python
sequence = build_runtime_behavior_sequence(profile, books, orders, reviews, cart_items)
prediction = self.model_service.predict(sequence)
retrieval = self.rag_pipeline.retrieve(
    question,
    behavior_segment=prediction["behavior_segment"],
    sequence_context=sequence,
    top_k=5,
)
```

```python
return {
    "answer": answer,
    "behavior_segment": behavior_segment,
    "probabilities": prediction.get("probabilities", {}),
    "model_name": prediction.get("model_name", "model_best"),
    "recommended_books": retrieval.get("recommended_books", recommended_books),
    "sources": retrieval["text_sources"],
    "graph_facts": retrieval["graph_facts"],
    "graph_paths": retrieval["graph_paths"],
    "feature_summary": feature_summary,
    "sequence_summary": prediction.get("sequence_summary", ""),
}
```

- [ ] **Step 4: Run test to verify orchestration passes**

Run: `python manage.py test app.tests.AdvisorSequenceRagTests -v 2`
Expected: PASS

- [ ] **Step 5: Run the broader advisor test suite**

Run: `python manage.py test app.tests -v 2`
Expected: PASS with chat/profile endpoints still returning the enriched contract.

- [ ] **Step 6: Commit**

```bash
git add advisor-service/app/services/features.py advisor-service/app/services/clients.py advisor-service/app/services/rag_pipeline.py advisor-service/app/services/prompting.py advisor-service/app/services/advisor.py advisor-service/app/views.py advisor-service/app/tests.py
git commit -m "feat: orchestrate sequence model with graph rag"
```

### Task 5: Surface recommendations and custom chat in the gateway

**Files:**
- Modify: `api-gateway/app/views.py`
- Modify: `api-gateway/app/templates/books.html`
- Modify: `api-gateway/app/templates/cart.html`
- Modify: `api-gateway/app/templates/base.html`
- Create: `api-gateway/app/templates/partials/advisor_panel.html`

- [ ] **Step 1: Write the failing gateway integration tests**

```python
class GatewayAdvisorUiTests(TestCase):
    @patch("app.views.requests.get")
    def test_books_page_renders_advisor_recommendations(self, get_mock):
        # configure upstream book + advisor responses
        response = self.client.get("/books/")
        self.assertContains(response, "Recommended for your behavior")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test app.tests.GatewayAdvisorUiTests -v 2`
Expected: FAIL because gateway pages do not yet render advisor recommendation UI.

- [ ] **Step 3: Add gateway advisor fetch helpers and template partial**

```python
def _fetch_advisor_profile(user_id):
    response = requests.get(f"{ADVISOR_SERVICE_URL}/advisor/profile/{user_id}/", timeout=10)
    if response.status_code != 200:
        return {"recommended_books": [], "behavior_segment": "casual_buyer"}
    return _normalize_advisor_payload(response.json())
```

```html
<section class="advisor-panel">
  <div class="advisor-panel__header">
    <h2>Recommended for your behavior</h2>
    <p>{{ advisor.behavior_segment }}</p>
  </div>
  {% for book in advisor.recommended_books %}
    <article class="advisor-book-pill">{{ book.title }}</article>
  {% endfor %}
</section>
```

- [ ] **Step 4: Run test to verify books/cart UI passes**

Run: `python manage.py test app.tests.GatewayAdvisorUiTests -v 2`
Expected: PASS

- [ ] **Step 5: Manually verify bookstore chat panel is visible**

Run: start gateway locally and open `/books/` and `/cart/<customer_id>/`
Expected: recommendation block appears, and chat UI is visually distinct from default ChatGPT-style layouts.

- [ ] **Step 6: Commit**

```bash
git add api-gateway/app/views.py api-gateway/app/templates/books.html api-gateway/app/templates/cart.html api-gateway/app/templates/base.html api-gateway/app/templates/partials/advisor_panel.html
git commit -m "feat: integrate advisor ui into gateway"
```

### Task 6: Verify deliverables and artifact generation end-to-end

**Files:**
- Modify: `advisor-service/app/tests.py`
- Modify: `advisor-service/requirements.txt`

- [ ] **Step 1: Add verification tests for artifact contract**

```python
class ArtifactContractTests(TestCase):
    def test_training_metadata_mentions_best_model(self):
        metadata = json.loads((MODEL_DIR / "model_metadata.json").read_text(encoding="utf-8"))
        self.assertIn("best_model_name", metadata)
```

- [ ] **Step 2: Run test to verify it fails before requirements/artifacts are finalized**

Run: `python manage.py test app.tests.ArtifactContractTests -v 2`
Expected: FAIL until artifacts are generated and metadata contract is finalized.

- [ ] **Step 3: Finalize requirements and rerun artifact pipeline**

```text
tensorflow
pandas
scikit-learn
matplotlib
neo4j
```

Run:

```bash
python manage.py prepare_behavior_data --seed 42
python manage.py train_behavior_model
python manage.py sync_behavior_graph
python manage.py test app.tests -v 2
```

Expected: all commands exit 0, artifacts exist, and Django tests pass.

- [ ] **Step 4: Verify submission-ready files exist**

Run:

```bash
dir advisor-service\app\data\training
dir advisor-service\app\data\models
dir advisor-service\app\data\knowledge_graph
```

Expected: dataset CSV, sample20 CSV, model artifacts, plots, and graph exports are present for the PDF write-up.

- [ ] **Step 5: Commit**

```bash
git add advisor-service/requirements.txt advisor-service/app/tests.py advisor-service/app/data/training advisor-service/app/data/models advisor-service/app/data/knowledge_graph
git commit -m "chore: verify ai ecommerce artifacts"
```
