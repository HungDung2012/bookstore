# Bookstore AI Graph RAG Upgrade Design

## Goal

Nang cap `advisor-service` tu muc demo don gian thanh mot module AI co cau truc ro rang trong source code, gom:

- `deep learning` cho phan loai hanh vi khach hang
- `graph-based knowledge base` de bieu dien tri thuc tu van
- `hybrid RAG` ket hop graph retrieval va text retrieval
- `integration` truc tiep voi he microservice e-commerce hien co

Muc tieu la de giang vien co the mo source code va chi ro tung phan AI trong du an, khong phai chi xem demo giao dien.

## Scope

Pham vi dot nang cap nay chi tap trung vao `advisor-service` va diem tich hop cua no vao `api-gateway`.

Nam trong pham vi:

- don dep merge conflict va thong nhat source hien co cua `advisor-service`
- giu lai behavior model nhung dua ve cau truc ro rang hon
- them graph knowledge base va graph retriever
- them hybrid RAG pipeline
- cap nhat API payload de tra ve thong tin giai thich day du hon
- bo sung test cho tung lop AI

Ngoai pham vi:

- khong dua Neo4j vao he thong
- khong lam distributed training
- khong dua event-driven pipeline cho advisor
- khong thay doi lon UX cua popup chat ngoai viec hien thi du lieu tu van giau hon neu can

## Recommended Architecture

Huong duoc chon la:

- `Deep learning` duoc train bang command rieng va predict trong runtime
- `Graph KB in code` duoc load tu JSON thanh node/edge va query ngay trong service
- `Hybrid RAG` gom graph traversal + text retrieval + answer synthesis

Ly do chon huong nay:

- de chi source code cho thay thay ro tung phan
- khong tang qua nhieu do phuc tap deploy
- van du “graph-based KB” dung nghia ma khong phu thuoc graph database ben ngoai
- giu duoc dong chay demo tren he microservice hien co

## Source Structure

`advisor-service` se duoc to chuc lai theo cac khoi sau.

### 1. Deep Learning Layer

Files chinh:

- `advisor-service/app/services/behavior_dataset.py`
- `advisor-service/app/services/features.py`
- `advisor-service/app/services/behavior_model.py`
- `advisor-service/app/management/commands/prepare_behavior_data.py`
- `advisor-service/app/management/commands/train_behavior_model.py`

Trach nhiem:

- `features.py`: rut dac trung hanh vi tu profile, order, review, cart, book catalog
- `behavior_dataset.py`: chuan hoa feature schema, vector order, labels, metadata
- `prepare_behavior_data.py`: xay dataset huan luyen tu du lieu e-commerce va pseudo-labels
- `train_behavior_model.py`: dinh nghia, train, va luu `model_behavior`
- `behavior_model.py`: load artifact va du doan `behavior_segment`

Yeu cau code:

- phai co model definition ro rang de chi cho thay thay phan deep learning
- artifact phai gom model file, feature names, labels, va metadata
- predict phai tra ve segment va probabilities

### 2. Graph Knowledge Base Layer

Files chinh:

- `advisor-service/app/services/graph_kb.py`
- `advisor-service/app/data/knowledge_graph/nodes.json`
- `advisor-service/app/data/knowledge_graph/edges.json`
- `advisor-service/app/data/knowledge_graph/facts.json`

Trach nhiem:

- bieu dien KB theo do thi gom `nodes` va `edges`
- ho tro cac loai node:
  - `segment`
  - `category`
  - `book_signal`
  - `service`
  - `policy`
  - `payment_method`
  - `shipping_status`
- ho tro cac loai edge:
  - `prefers`
  - `recommended_for`
  - `related_to`
  - `governed_by`
  - `explained_by`
  - `next_step_for`

Yeu cau code:

- can co class ro rang nhu `GraphNode`, `GraphEdge`, `GraphKnowledgeBase`
- can co API load graph, adjacency map, traversal, va rank facts
- graph phai doc lap voi LLM de khi thay hoi “graph o dau” co the chi thang file va data

### 3. Text Knowledge Layer

Files chinh:

- `advisor-service/app/services/knowledge_base.py`
- `advisor-service/app/services/text_retriever.py`
- `advisor-service/app/data/knowledge_base/*.json`

Trach nhiem:

- giu FAQ, policy, category guidance, service explanation dang document text
- retrieve cac doan text lien quan den cau hoi nguoi dung
- bo sung metadata nhu:
  - `doc_type`
  - `target_segment`
  - `category`
  - `service_scope`

### 4. Hybrid RAG Layer

Files chinh:

- `advisor-service/app/services/graph_retriever.py`
- `advisor-service/app/services/text_retriever.py`
- `advisor-service/app/services/rag_pipeline.py`
- `advisor-service/app/services/prompting.py`

Trach nhiem:

- `graph_retriever.py`: tim facts va path lien quan tu graph dua tren `behavior_segment`, query intent, va category signals
- `text_retriever.py`: rank document text theo query va metadata
- `rag_pipeline.py`: hop nhat graph facts va text context thanh context cuoi cung
- `prompting.py`: build prompt va fallback answer

Hybrid RAG flow:

1. nhan `question` va `user_id`
2. predict `behavior_segment`
3. graph retrieval lay:
   - segment facts
   - category guidance
   - policy/payment/shipping relation
4. text retrieval lay:
   - FAQ
   - policy
   - category/service explanation
5. compose context
6. generate answer bang LLM neu co key, hoac deterministic builder neu khong co

### 5. Advisor Orchestration Layer

Files chinh:

- `advisor-service/app/services/clients.py`
- `advisor-service/app/services/advisor.py`
- `advisor-service/app/views.py`

Trach nhiem:

- `clients.py`: lay du lieu that tu `user-service`, `book-service`, `order-service`, `cart-service`, `review-service`
- `advisor.py`: dieu phoi toan bo pipeline AI
- `views.py`: expose API
  - `POST /advisor/chat/`
  - `GET /advisor/profile/<user_id>/`

`advisor.py` phai la noi co the chi ro duoc pipeline sau:

`e-commerce data -> features -> behavior model -> graph retrieval -> text retrieval -> RAG answer`

## End-to-End Data Flow

### Chat Flow

1. `api-gateway` gui `user_id` va `question` den `advisor-service`
2. `advisor-service` goi cac microservice de lay profile, orders, reviews, cart, books
3. feature engineering xay vector hanh vi
4. `model_behavior` du doan `behavior_segment`
5. `graph_retriever` lay tri thuc do thi lien quan
6. `text_retriever` lay tai lieu text lien quan
7. `rag_pipeline` hop nhat context
8. `prompting` tao prompt
9. LLM sinh cau tra loi, hoac fallback builder tao answer co cau truc
10. ket qua tra ve cho `api-gateway`

### Profile Flow

1. gateway goi `/advisor/profile/<user_id>/`
2. advisor tinh feature va du doan segment
3. API tra:
   - `behavior_segment`
   - `probabilities`
   - `feature_summary`
   - `dominant_categories`
   - `graph_signals`

## API Response Shape

`POST /advisor/chat/` se tra ve payload day du hon:

- `answer`
- `behavior_segment`
- `probabilities`
- `recommended_books`
- `sources`
- `feature_summary`
- `graph_facts`
- `graph_paths`

Muc dich:

- de giao dien chat hien thi duoc
- de de dang giai thich trong luc bao ve do an

## Integration With E-commerce

Advisor se duoc tich hop voi cac service sau:

- `user-service`: profile, role
- `book-service`: books, categories, publishers
- `order-service`: order history
- `cart-service`: cart intent
- `review-service`: review signals
- `api-gateway`: chat popup va advisor profile proxy

Tac dong len he thong:

- khong can thay doi bounded context chinh cua bookstore
- `advisor-service` tiep tuc dong vai tro `Advisory Context`
- advisor dung du lieu tu cac context khac de sinh tri thuc tu van

## Testing Strategy

Can co test ro rang cho tung lop.

### Unit Tests

- feature engineering
- behavior dataset normalization
- behavior model prediction va artifact loading
- graph KB loading
- graph traversal va fact ranking
- text retrieval ranking
- rag pipeline context composition

### Service Tests

- `/advisor/chat/` tra payload day du
- `/advisor/profile/<user_id>/` tra behavior profile
- anonymous chat van hoat dong voi fallback profile

### Integration Tests

- mock du lieu tu microservices
- verify pipeline ra dung `behavior_segment`
- verify graph facts va text sources cung duoc tra ve

## Deployment Notes

Ban nang cap nay van giu `advisor-service` la service rieng trong:

- `docker-compose.yml`
- `render.yaml`

Runtime co the tiep tuc nhe hon cho demo, nhung source code van phai giu day du:

- model definition
- training commands
- graph KB
- rag pipeline

Neu dependency train-time nang, cho phep tach `runtime` va `train-time` nhung khong duoc lam mo source code.

## Success Criteria

Ban nang cap duoc xem la dat neu:

- source code khong con merge conflict trong `advisor-service`
- co file ro rang cho deep learning, graph KB, hybrid RAG, integration
- `advisor-service` tra ve ket qua chat co `behavior_segment`, `sources`, `graph_facts`
- co test cho tung lop chinh
- giao vien co the duoc chi den tung file de thay:
  - deep learning o dau
  - graph-based KB o dau
  - RAG o dau
  - integration voi e-commerce o dau

## Risks And Controls

- Risk: code AI qua nang de deploy
  - Control: tach train-time artifact voi runtime neu can
- Risk: graph KB bi bien thanh mapping don gian
  - Control: bat buoc co node, edge, traversal, va graph facts tra ra trong API
- Risk: RAG chi la prompt thuong
  - Control: tach rieng `graph_retriever`, `text_retriever`, `rag_pipeline`
- Risk: khong chi duoc source cho thay
  - Control: to chuc module ro rang va co tai lieu DDD/AI mapping
