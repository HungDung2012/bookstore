# Bookstore AI Ecommerce Upgrade Design

## Goal

Nang cap `advisor-service` thanh mot module AI e-commerce co chieu sau hoc thuat va van tich hop duoc vao he microservice hien co, de dap ung truc tiep cac muc bai nop:

- sinh `data_user500.csv` voi `500` user va `8` behaviors
- huan luyen va danh gia `RNN`, `LSTM`, `biLSTM`
- chon `model_best` dua tren metric phu hop
- xay dung `KB_Graph` bang `Neo4j`
- xay dung `RAG + chat` dua tren `KB_Graph`
- tich hop recommendation va chat vao giao dien e-commerce

Muc tieu phu la de giang vien co the doc source code va nhin thay ro:

- logic sinh du lieu
- pipeline sequence modeling
- graph modeling va truy van Neo4j that
- luong `prediction -> retrieval -> recommendation -> chat`

## Scope

Nam trong pham vi:

- nang cap `advisor-service` de ho tro du lieu chuoi hanh vi thay vi chi feature vector phang
- them command sinh `data_user500.csv` va cac artifact phuc vu nop bai
- train va danh gia 3 mo hinh `SimpleRNN`, `LSTM`, `Bidirectional(LSTM)` bang `TensorFlow/Keras`
- luu `model_best` va metadata danh gia
- tich hop `Neo4j` runtime vao `advisor-service`
- sinh graph tu dataset va du lieu sach de import/query trong Neo4j
- nang cap `RAG` de uu tien graph retrieval
- tich hop recommendation/chat vao `api-gateway`
- bo sung test cho cac lop AI va API advisor

Ngoai pham vi:

- khong lam distributed training
- khong xay pipeline streaming/event bus
- khong toi uu hieu nang production-grade cho training
- khong phu thuoc vao giao dien admin phuc tap moi

## Recommended Architecture

Huong duoc chon la nang cap truc tiep tren kien truc hien co cua `advisor-service`, thay vi tach thanh mot module hoc thuat doc lap.

Ly do chon:

- repo da co san `behavior_dataset`, `advisor`, `rag_pipeline`, `graph_kb`, va diem tich hop gateway
- thay doc code se thay mot he thong thong nhat, khong phai hai code path rieng biet
- co the chi ro duoc phan nang cap tu behavior classifier cu sang sequence AI + graph RAG
- van giu duoc demo end-to-end trong he e-commerce

Kien truc tong the:

`user behavior data -> sequence encoder -> RNN/LSTM/biLSTM -> model_best -> segment prediction -> Neo4j retrieval -> hybrid RAG -> product recommendations + chat UI`

## Source Structure

### 1. Behavior Dataset Layer

Files chinh:

- `advisor-service/app/services/behavior_dataset.py`
- `advisor-service/app/management/commands/prepare_behavior_data.py`
- `advisor-service/app/data/training/data_user500.csv`
- `advisor-service/app/data/training/data_user500_sample20.csv`

Trach nhiem:

- dinh nghia schema cho sequence dataset gom `500` user
- chuan hoa `8` timesteps behavior cho moi user
- export CSV day du va file 20 dong mau de dua vao PDF
- luu metadata cua label map, behavior vocab, feature dimensions

Thiet ke du lieu:

- moi dong tuong ung mot user
- gom thong tin nen:
  - `user_id`
  - `age_group`
  - `favorite_category`
  - `price_sensitivity`
  - `membership_tier`
- gom `8` behavior steps theo thu tu thoi gian:
  - `step_1_behavior` ... `step_8_behavior`
  - `step_1_category` ... `step_8_category`
  - `step_1_price_band` ... `step_8_price_band`
  - `step_1_duration` ... `step_8_duration`
- co nhan `label` cho segment dich:
  - `impulse_buyer`
  - `careful_researcher`
  - `discount_hunter`
  - `loyal_reader`
  - `window_shopper`

Tap behavior duoc gioi han ro rang thanh `8` hanh vi e-commerce:

- `view_home`
- `search`
- `view_detail`
- `add_to_cart`
- `remove_from_cart`
- `wishlist`
- `checkout`
- `review`

Yeu cau code:

- du lieu phai du tinh da dang de 3 model hoc duoc pattern
- co random seed co dinh de tai lap ket qua
- co helper tao sample 20 dong phuc vu bao cao

### 2. Sequence Modeling Layer

Files chinh:

- `advisor-service/app/services/behavior_model.py`
- `advisor-service/app/management/commands/train_behavior_model.py`
- `advisor-service/app/data/models/model_rnn.keras`
- `advisor-service/app/data/models/model_lstm.keras`
- `advisor-service/app/data/models/model_bilstm.keras`
- `advisor-service/app/data/models/model_best.keras`
- `advisor-service/app/data/models/model_comparison.json`
- `advisor-service/app/data/models/model_metadata.json`
- `advisor-service/app/data/models/plots/*.png`

Trach nhiem:

- encode CSV thanh tensor `(samples, timesteps=8, feature_dim)`
- xay 3 model:
  - `SimpleRNN`
  - `LSTM`
  - `Bidirectional(LSTM)`
- train, evaluate, luu artifact rieng cho tung model
- chon `model_best` theo `macro_f1`, neu hoa thi dung `accuracy`
- cung cap runtime service de load `model_best` va suy luan segment

Yeu cau model:

- bat buoc dung `TensorFlow/Keras` that, khong co fallback model khac
- co train/validation split ro rang
- luu metrics:
  - `accuracy`
  - `precision_macro`
  - `recall_macro`
  - `f1_macro`
- luu:
  - confusion matrix
  - classification report
  - training history plots
  - comparison plot giua 3 model

Yeu cau runtime:

- `BehaviorModelService` phai load duoc `model_best`
- predict tra:
  - `behavior_segment`
  - `probabilities`
  - `model_name`
  - `sequence_summary`

### 3. Feature and Event Extraction Layer

Files chinh:

- `advisor-service/app/services/features.py`
- `advisor-service/app/services/clients.py`

Trach nhiem:

- trich xuat hanh vi user that tu:
  - `book-service`
  - `cart-service`
  - `order-service`
  - `review-service`
- quy doi cac tin hieu do ve chuoi `8` buoc gan nhat hoac chuoi tong hop
- tao sequence runtime cho prediction trong app

Nguyen tac mapping:

- `search` tu query tim sach
- `view_detail` tu xem chi tiet san pham
- `add_to_cart` va `remove_from_cart` tu bien dong gio hang
- `checkout` tu don hang thanh cong
- `review` tu danh gia sach

Neu du lieu song khong du `8` buoc:

- pad ve do dai 8 theo quy tac ro rang
- metadata phai ghi ro padded steps de tranh nham lan khi giai thich

### 4. Neo4j Graph Layer

Files chinh:

- `advisor-service/app/services/graph_kb.py`
- `advisor-service/app/services/graph_retriever.py`
- `advisor-service/app/management/commands/sync_behavior_graph.py`
- `advisor-service/app/data/knowledge_graph/nodes.json`
- `advisor-service/app/data/knowledge_graph/edges.json`
- `advisor-service/app/data/knowledge_graph/facts.json`
- `advisor-service/app/data/knowledge_graph/import.cypher`

Trach nhiem:

- dinh nghia graph object trong code cho test va export
- dong bo graph vao `Neo4j` that bang command rieng
- cho phep app truy van `Neo4j` runtime khi chat/recommend
- luu JSON export song song de de nop bai va chup anh graph

Node chinh:

- `User`
- `BehaviorSequence`
- `BehaviorEvent`
- `Segment`
- `Book`
- `Category`
- `Author`
- `QueryIntent`

Quan he chinh:

- `(:User)-[:PERFORMED]->(:BehaviorSequence)`
- `(:BehaviorSequence)-[:HAS_EVENT]->(:BehaviorEvent)`
- `(:User)-[:BELONGS_TO]->(:Segment)`
- `(:User)-[:INTERESTED_IN]->(:Category)`
- `(:Segment)-[:PREFERS]->(:Category)`
- `(:Segment)-[:LIKES]->(:Book)`
- `(:Book)-[:IN_CATEGORY]->(:Category)`
- `(:Book)-[:WRITTEN_BY]->(:Author)`
- `(:QueryIntent)-[:MATCHES_SEGMENT]->(:Segment)`

Yeu cau code:

- `graph_kb.py` giu cac class graph de phuc vu export va test
- them `Neo4jGraphService` de:
  - mo ket noi bang env vars
  - create constraints/indexes
  - import nodes/edges/facts
  - query related books/categories/paths
- phai co script/command de rebuild graph tu dataset moi

### 5. Hybrid RAG Layer

Files chinh:

- `advisor-service/app/services/rag_pipeline.py`
- `advisor-service/app/services/text_retriever.py`
- `advisor-service/app/services/knowledge_base.py`
- `advisor-service/app/services/prompting.py`
- `advisor-service/app/data/knowledge_base/*.json`

Trach nhiem:

- uu tien lay context tu `Neo4j`
- ghep them text KB de bo sung explanation va policy
- tra ve `graph_facts`, `graph_paths`, `text_sources`
- xay prompt nhan manh ly do goi y theo segment va graph

RAG flow:

1. nhan `question` va `user_id`
2. build runtime behavior sequence
3. `model_best` predict `behavior_segment`
4. `Neo4jGraphService` query:
   - segment-related categories
   - books phu hop
   - graph paths giai thich
5. `text_retriever` lay policy, FAQ, segment advice lien quan
6. `rag_pipeline` dedupe, score, va compose context
7. `prompting` build answer cho LLM
8. neu khong co API key, fallback answer van phai dua tren graph context thay vi tra loi chung chung

### 6. Advisor Orchestration Layer

Files chinh:

- `advisor-service/app/services/advisor.py`
- `advisor-service/app/views.py`
- `advisor-service/app/serializers.py`

Trach nhiem:

- dieu phoi toan bo pipeline AI
- expose API cho gateway
- bo sung payload giai thich de phuc vu UI va bao cao

`POST /advisor/chat/` tra:

- `answer`
- `behavior_segment`
- `probabilities`
- `model_name`
- `recommended_books`
- `sources`
- `graph_facts`
- `graph_paths`
- `feature_summary`
- `sequence_summary`

`GET /advisor/profile/<user_id>/` tra:

- `behavior_segment`
- `probabilities`
- `model_name`
- `recommended_books`
- `feature_summary`
- `sequence_summary`

### 7. E-commerce Integration Layer

Files chinh:

- `api-gateway/app/views.py`
- `api-gateway/app/templates/books.html`
- `api-gateway/app/templates/cart.html`
- co the them `api-gateway/app/templates/advisor_chat.html` neu can tach rieng
- `api-gateway/app/templates/base.html`

Trach nhiem:

- khi user search hoac vao danh sach sach, hien block goi y theo AI
- khi user them vao gio hang, hien goi y san pham lien quan
- hien giao dien chat rieng trong e-commerce, khong mo phong giao dien mac dinh cua ChatGPT

Yeu cau UI:

- giao dien chat phai la bubble/message panel tu thiet ke cho bookstore
- hien duoc:
  - tin nhan user
  - cau tra loi advisor
  - recommended books
  - ly do goi y gon
- UI recommendation tren `books` va `cart` phai de nhan thay trong demo

## End-to-End Data Flow

### Training Flow

1. chay command tao `data_user500.csv`
2. validate schema va tao sample 20 dong
3. chay command train 3 models
4. evaluate va so sanh metrics
5. chon `model_best`
6. sinh plots va metadata de phuc vu nop bai
7. sync graph sang `Neo4j`

### Runtime Chat Flow

1. `api-gateway` gui `user_id` va `question`
2. `advisor-service` lay du lieu user va interaction lien quan
3. build sequence 8 steps
4. `model_best` du doan segment
5. query `Neo4j` lay paths/facts/books/category
6. retrieve text context bo sung
7. build prompt va generate answer
8. gateway render answer va danh sach sach goi y

### Runtime Recommendation Flow

1. user vao trang `books` hoac `cart`
2. gateway goi advisor profile/chat API phu hop
3. advisor tra segment + recommended books
4. gateway hien block recommendation ngay tren giao dien e-commerce

## Evaluation Strategy

Model selection duoc danh gia bang:

- `accuracy`
- `precision_macro`
- `recall_macro`
- `f1_macro`
- confusion matrix
- history plot cua train/validation

Tieu chi chon `model_best`:

1. cao nhat theo `f1_macro`
2. neu bang nhau thi xet `accuracy`
3. neu tiep tuc bang nhau thi uu tien `biLSTM`, sau do `LSTM`, sau do `RNN` vi kha nang mo hinh hoa chuoi manh hon

Ly do:

- bai toan nhieu class va can can bang giua cac segment, nen `macro_f1` phan anh chat luong tot hon chi dung accuracy

## Testing Strategy

### Unit Tests

- test sinh schema va CSV cho `500` user, `8` behaviors
- test sequence encoder tao dung tensor shape
- test model selection logic chon dung `model_best`
- test graph export tao du node/edge/fact
- test Neo4j query adapter map ket qua dung format
- test RAG pipeline compose context khong trung lap

### Service Tests

- `/advisor/chat/` tra du cac truong moi
- `/advisor/profile/<user_id>/` tra segment + model name + recommendations
- fallback khi LLM khong co key van dua tren graph context

### Manual Verification

- command sinh duoc `data_user500.csv`
- command train sinh 3 model + 1 model_best + plots
- command sync graph nap du lieu vao `Neo4j`
- gateway hien recommendation tren `books` va `cart`
- giao dien chat bookstore hoat dong

## Deliverables For Submission

He thong phai sinh hoac duy tri duoc cac artifact de dua vao file PDF:

- mo ta `AISERVICE`
- `data_user500.csv`
- `data_user500_sample20.csv`
- code va anh cho cau `2a`
- anh graph va 20 dong graph data cho cau `2b`
- tai lieu + anh cho `2c`, `2d`

Artifact uu tien luu trong repo:

- `advisor-service/app/data/training/`
- `advisor-service/app/data/models/`
- `advisor-service/app/data/knowledge_graph/exports/`

## Risks and Constraints

- `TensorFlow` va `Neo4j` la hai phu thuoc chinh, can khai bao ro trong `requirements.txt` va config env
- sequence runtime tu microservice data that co the khong day du nhu dataset synth, nen can quy tac pad/truncate ro rang
- recommendation trong gateway phai tranh lam cham trang qua muc, nen co timeout va fallback payload ngan

## Acceptance Criteria

Cong viec duoc xem la dat khi:

- repo sinh duoc `data_user500.csv` voi `500` user va `8` behaviors
- co 3 model `RNN`, `LSTM`, `biLSTM` duoc train bang `TensorFlow/Keras`
- co metadata so sanh va `model_best`
- `Neo4j` duoc ket noi va query that tu `advisor-service`
- chat va RAG dua tren graph context thay vi text-only
- giao dien e-commerce hien recommendation o `books` hoac `cart`
- giao dien chat rieng cua bookstore hoat dong duoc
- cac artifact can cho PDF duoc tao ra trong repo
