# AISERVICE02 - BOOKSTORE AI E-COMMERCE

## 1. Trang bìa

**TRƯỜNG / KHOA:** ..........................................................

**MÔN HỌC:** Trí tuệ nhân tạo ứng dụng / AI Service

**ĐỀ TÀI:** Xây dựng AI Service cho hệ e-commerce sách

**TÊN FILE NỘP:** `aiservice02_lớp.nhóm_tênho.PDF`

**LỚP:** ..........................................................

**NHÓM:** ..........................................................

**HỌ VÀ TÊN:** ..........................................................

**MSSV:** ..........................................................

**GIẢNG VIÊN:** ..........................................................

**NGÀY NỘP:** 20/04/2026

---

## 2. Mô tả AISERVICE

### 2.1. Mục tiêu

AISERVICE được xây dựng để nâng cấp hệ thống e-commerce bán sách theo hướng cá nhân hóa hành vi người dùng. Hệ thống thực hiện 4 chức năng chính:

1. Sinh tập dữ liệu `data_user500.csv` gồm 500 người dùng với chuỗi 8 hành vi mua sắm.
2. Huấn luyện 3 mô hình học sâu `SimpleRNN`, `LSTM`, `biLSTM` để phân loại hành vi người dùng.
3. Xây dựng Knowledge Base Graph bằng Neo4j từ dữ liệu hành vi và tri thức sản phẩm.
4. Xây dựng RAG + Chatbot và tích hợp vào giao diện e-commerce để gợi ý sách theo ngữ cảnh.

### 2.2. Kiến trúc tổng quát

- `advisor-service` chịu trách nhiệm sinh dữ liệu, train mô hình, suy luận hành vi, truy vấn graph, và sinh câu trả lời chat.
- `api-gateway` chịu trách nhiệm hiển thị recommendation shelf, cart suggestion và giao diện chatbot riêng cho người dùng.
- `Neo4j` lưu tri thức dạng graph gồm các node như `Segment`, `Category`, `Service`, `Policy`, `Book`.

### 2.3. Chuỗi 8 hành vi được sử dụng

Hệ thống mô hình hóa 8 hành vi e-commerce điển hình:

1. `view_home`
2. `search`
3. `view_detail`
4. `add_to_cart`
5. `remove_from_cart`
6. `wishlist`
7. `checkout`
8. `review`

### 2.4. Các nhãn phân loại hành vi

Mô hình dự đoán 5 nhóm hành vi:

1. `impulse_buyer`
2. `careful_researcher`
3. `discount_hunter`
4. `loyal_reader`
5. `window_shopper`

### 2.5. Các file đầu ra chính

- Dataset: [data_user500.csv](../advisor-service/app/data/training/data_user500.csv)
- Sample 20 dòng: [data_user500_sample20.csv](../advisor-service/app/data/training/data_user500_sample20.csv)
- Mô hình tốt nhất: [model_best.keras](../advisor-service/app/data/models/model_best.keras)
- So sánh mô hình: [model_comparison.json](../advisor-service/app/data/models/model_comparison.json)
- Plot so sánh: [model_comparison.png](../advisor-service/app/data/models/plots/model_comparison.png)
- Graph artifacts:
  - [nodes.json](../advisor-service/app/data/knowledge_graph/nodes.json)
  - [edges.json](../advisor-service/app/data/knowledge_graph/edges.json)
  - [facts.json](../advisor-service/app/data/knowledge_graph/facts.json)
  - [import.cypher](../advisor-service/app/data/knowledge_graph/import.cypher)

---

## 3. Copy 20 dòng data

Trích 20 dòng đầu của file `data_user500_sample20.csv`:

```csv
user_id,age_group,favorite_category,price_sensitivity,membership_tier,step_1_behavior,step_2_behavior,step_3_behavior,step_4_behavior,step_5_behavior,step_6_behavior,step_7_behavior,step_8_behavior,step_1_category,step_2_category,step_3_category,step_4_category,step_5_category,step_6_category,step_7_category,step_8_category,step_1_price_band,step_2_price_band,step_3_price_band,step_4_price_band,step_5_price_band,step_6_price_band,step_7_price_band,step_8_price_band,step_1_duration,step_2_duration,step_3_duration,step_4_duration,step_5_duration,step_6_duration,step_7_duration,step_8_duration,label
1,36-45,discounts,low,gold,view_home,add_to_cart,checkout,review,view_detail,wishlist,search,remove_from_cart,novelty,electronics,electronics,general,electronics,general,general,electronics,high,low,mid,high,mid,high,high,mid,14,13,17,17,9,3,9,14,impulse_buyer
2,18-25,technology,high,bronze,view_home,view_detail,wishlist,review,view_detail,view_home,checkout,review,literature,literature,literature,literature,general,books,books,literature,high,medium,high,low,low,medium,low,low,6,11,4,13,8,5,15,9,loyal_reader
3,55+,literature,medium,platinum,search,view_home,add_to_cart,checkout,view_detail,wishlist,review,remove_from_cart,mid,high,high,high,high,high,high,low,12,5,10,6,8,9,5,10,15,11,14,11,3,18,16,11,impulse_buyer
4,18-25,discounts,low,bronze,view_detail,view_home,wishlist,review,checkout,view_detail,view_home,review,medium,high,low,low,low,low,medium,low,8,10,11,6,5,7,12,3,8,13,5,9,16,9,9,5,loyal_reader
5,26-35,discounts,medium,gold,view_home,wishlist,view_detail,review,view_detail,checkout,view_home,review,15,10,9,9,8,10,8,6,review,wishlist,cart,checkout,highlight,recommendation,wishlist,search,15,16,6,3,18,4,8,15,loyal_reader
6,26-35,literature,low,bronze,search,view_home,add_to_cart,remove_from_cart,wishlist,checkout,search,review,general,general,electronics,discounts,electronics,discounts,electronics,books,low,low,high,high,mid,high,low,high,15,13,17,17,6,15,7,4,discount_hunter
7,55+,technology,high,gold,view_home,view_detail,add_to_cart,checkout,wishlist,search,review,remove_from_cart,12,14,10,11,12,13,8,3,add_to_cart,checkout,share,recommendation,browse,cart,recommendation,tap,3,5,10,7,18,18,16,16,impulse_buyer
8,46-55,technology,medium,platinum,view_home,search,view_detail,wishlist,remove_from_cart,view_home,search,view_detail,books,general,general,technology,books,general,electronics,technology,high,low,mid,high,high,low,low,mid,14,12,6,17,17,18,11,18,window_shopper
9,46-55,business,high,platinum,search,view_detail,search,wishlist,view_detail,search,review,view_detail,technology,literature,literature,general,business,business,general,general,medium,low,high,high,medium,low,medium,medium,15,18,14,17,5,10,6,18,careful_researcher
10,18-25,technology,high,gold,view_detail,search,wishlist,search,view_detail,review,search,wishlist,low,medium,high,medium,medium,high,low,high,10,8,17,11,10,8,5,14,3,9,4,8,13,10,16,8,careful_researcher
11,26-35,general,medium,gold,view_home,search,wishlist,add_to_cart,checkout,remove_from_cart,review,search,high,mid,low,high,mid,low,high,mid,6,5,6,4,7,5,4,5,13,10,16,10,9,8,7,7,discount_hunter
12,18-25,business,high,gold,search,search,view_detail,wishlist,review,view_detail,search,checkout,14,12,9,7,6,8,9,6,compare,compare,wishlist,cart,compare,highlight,browse,compare,16,13,5,12,11,4,11,7,careful_researcher
13,36-45,literature,medium,platinum,view_home,add_to_cart,checkout,review,view_detail,wishlist,search,remove_from_cart,novelty,electronics,electronics,general,general,electronics,books,books,low,low,mid,high,mid,low,mid,high,5,6,17,14,18,12,14,8,impulse_buyer
14,55+,general,medium,silver,search,view_home,wishlist,view_detail,remove_from_cart,search,view_home,wishlist,high,high,low,low,mid,low,high,mid,3,4,5,11,6,4,5,6,8,17,9,14,10,6,13,14,window_shopper
15,18-25,literature,high,bronze,view_home,view_detail,search,wishlist,view_home,remove_from_cart,search,view_detail,5,6,10,4,3,4,9,4,browse,save,browse,browse,browse,browse,return_visit,browse,13,12,15,16,15,12,11,4,window_shopper
16,46-55,discounts,low,platinum,search,add_to_cart,view_home,wishlist,remove_from_cart,checkout,search,review,6,7,6,4,10,5,10,9,sort,compare,add_to_cart,coupon,share,repeat_visit,browse,deal,4,18,15,12,4,15,15,10,discount_hunter
17,36-45,literature,high,platinum,search,view_home,add_to_cart,remove_from_cart,wishlist,checkout,search,review,general,general,general,discounts,electronics,books,electronics,discounts,high,mid,high,high,low,mid,mid,high,10,9,13,18,11,10,16,7,discount_hunter
18,36-45,business,low,platinum,search,view_detail,search,wishlist,view_detail,search,review,view_detail,technology,general,literature,technology,technology,business,general,literature,medium,low,high,low,high,medium,low,medium,17,14,5,13,18,9,4,12,careful_researcher
19,26-35,literature,medium,gold,view_home,view_detail,wishlist,review,view_detail,view_home,checkout,review,literature,literature,general,books,literature,literature,books,books,low,high,medium,medium,high,medium,high,medium,11,12,16,9,11,9,11,14,loyal_reader
20,55+,technology,medium,platinum,view_detail,view_home,wishlist,review,checkout,view_detail,view_home,review,medium,medium,low,low,high,medium,high,low,15,7,11,12,8,10,5,6,6,3,18,12,6,11,14,13,loyal_reader
```

Nhận xét:

- Dữ liệu không còn là vector tĩnh mà là chuỗi 8 bước theo thời gian.
- Mỗi user có profile nền, category, mức giá, thời gian tương tác và nhãn hành vi.
- Tập dữ liệu phù hợp cho các mô hình học chuỗi như RNN và LSTM.

---

## 4. Câu 2a - Xây dựng 3 mô hình RNN, LSTM, biLSTM để dự đoán và phân loại

### 4.1. Ý tưởng thực hiện

Từ file `data_user500.csv`, dữ liệu được encode thành tensor 3 chiều:

- `samples = 500`
- `timesteps = 8`
- `feature_dim = số chiều sau khi one-hot các trường profile + behavior + category + price_band + duration`

Pipeline huấn luyện thực hiện các bước:

1. Đọc dữ liệu từ CSV.
2. Chia `train / validation / test`.
3. Fit encoder trên tập train.
4. Huấn luyện 3 mô hình:
   - `SimpleRNN`
   - `LSTM`
   - `Bidirectional(LSTM)`
5. Tính các độ đo `accuracy`, `precision_macro`, `recall_macro`, `f1_macro`.
6. So sánh trên validation rồi chọn `model_best`.
7. Đánh giá lại trên holdout test.

### 4.2. Code chính của câu 2a

File: [behavior_model.py](../advisor-service/app/services/behavior_model.py)

```python
def build_sequence_model(model_kind, timesteps, feature_dim, output_dim):
    if any(
        component is None
        for component in (Sequential, Dense, Dropout, Input, SimpleRNN, LSTM, Bidirectional)
    ):
        raise RuntimeError("TensorFlow is required to build the sequence behavior model.")

    layers = [Input(shape=(timesteps, feature_dim))]
    if model_kind == "simple_rnn":
        layers.extend([SimpleRNN(32), Dropout(0.1)])
    elif model_kind == "lstm":
        layers.extend([LSTM(32), Dropout(0.1)])
    elif model_kind == "bilstm":
        layers.extend([Bidirectional(LSTM(32)), Dropout(0.1)])
    else:
        raise ValueError(f"Unknown sequence model kind: {model_kind}")

    layers.extend([Dense(32, activation="relu"), Dense(output_dim, activation="softmax")])
    model = Sequential(layers)
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model
```

File: [train_behavior_model.py](../advisor-service/app/management/commands/train_behavior_model.py)

```python
def _select_best_model(model_metrics):
    if not model_metrics:
        raise CommandError("No model metrics were produced.")

    preference = {name: index for index, name in enumerate(SEQUENCE_MODEL_PREFERENCE[::-1])}

    def sort_key(item):
        name, metrics = item
        return (
            float(metrics.get("f1_macro", 0.0)),
            float(metrics.get("accuracy", 0.0)),
            preference.get(name, -1),
        )

    return max(model_metrics.items(), key=sort_key)[0]
```

### 4.3. Kết quả đánh giá 3 mô hình

Nguồn số liệu: [model_comparison.json](../advisor-service/app/data/models/model_comparison.json)

| Model | Validation Accuracy | Validation F1-macro | Test Accuracy | Test F1-macro |
|---|---:|---:|---:|---:|
| SimpleRNN | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| LSTM | 0.9600 | 0.9600 | 0.9600 | 0.9600 |
| biLSTM | 0.9600 | 0.9597 | 0.9300 | 0.9286 |

### 4.4. Nhận xét và lựa chọn mô hình tốt nhất

Mô hình được chọn là `SimpleRNN` và lưu thành [model_best.keras](../advisor-service/app/data/models/model_best.keras).

Giải thích:

- `SimpleRNN` đạt `accuracy = 1.0` và `f1_macro = 1.0` trên cả validation và test.
- `LSTM` cho kết quả tốt nhưng thấp hơn `SimpleRNN`.
- `biLSTM` có độ mạnh về lý thuyết, tuy nhiên trên bộ dữ liệu hiện tại lại cho kết quả holdout test thấp hơn.
- Vì bài toán có chuỗi độ dài ngắn là 8 bước, `SimpleRNN` đã đủ khả năng nắm bắt mẫu hành vi và cho kết quả tốt nhất.

Kết luận: `model_best = SimpleRNN`.

### 4.5. Ảnh cần chèn vào báo cáo

Chèn các ảnh sau:

1. [model_comparison.png](../advisor-service/app/data/models/plots/model_comparison.png)
2. [training_history_simple_rnn.png](../advisor-service/app/data/models/plots/training_history_simple_rnn.png)
3. [training_history_lstm.png](../advisor-service/app/data/models/plots/training_history_lstm.png)
4. [training_history_bilstm.png](../advisor-service/app/data/models/plots/training_history_bilstm.png)

Gợi ý caption:

- Hình 1. So sánh độ chính xác và F1-macro của 3 mô hình.
- Hình 2. Training history của mô hình SimpleRNN.
- Hình 3. Training history của mô hình LSTM.
- Hình 4. Training history của mô hình biLSTM.

---

## 5. Câu 2b - Xây dựng Knowledge Base Graph (KB_Graph) với Neo4j

### 5.1. Ý tưởng xây dựng graph

Từ tập dữ liệu hành vi và tri thức sản phẩm, hệ thống xây dựng KB_Graph với các loại node:

- `Segment`
- `Category`
- `Service`
- `Policy`
- `Book`

Các cạnh chính:

- `Segment -> Category`
- `Segment -> Service`
- `Category -> Service`
- `GraphFact -> GraphNode`

Graph này được dùng để:

1. Giải thích vì sao hệ thống gợi ý sản phẩm.
2. Bổ sung ngữ cảnh cho RAG.
3. Hỗ trợ chatbot trả lời theo hành vi người dùng.

### 5.2. Code chính của câu 2b

File: [graph_kb.py](../advisor-service/app/services/graph_kb.py)

```python
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
}
```

```python
class Neo4jGraphService:
    NODE_SYNC_QUERY = """
UNWIND $nodes AS node
MERGE (n:GraphNode {id: node.id})
SET n.type = node.type,
    n.label = node.label,
    n.metadata = node.metadata
RETURN count(n) AS node_count
"""
```

### 5.3. Copy 20 dòng graph artifact

Trích 20 dòng đầu của file [import.cypher](../advisor-service/app/data/knowledge_graph/import.cypher):

```cypher
// Behavior graph import script.
// The management command writes this artifact alongside nodes.json, edges.json, and facts.json.

UNWIND $nodes AS node
MERGE (n:GraphNode {id: node.id})
SET n.type = node.type,
    n.label = node.label,
    n.metadata = node.metadata;

UNWIND $edges AS edge
MATCH (source:GraphNode {id: edge.source})
MATCH (target:GraphNode {id: edge.target})
MERGE (source)-[r:RELATED_TO {relation: edge.relation}]->(target)
SET r.weight = edge.weight,
    r.metadata = edge.metadata;

UNWIND $facts AS fact
MATCH (node:GraphNode {id: fact.node_id})
MERGE (f:GraphFact {id: fact.id})
SET f.relation = fact.relation,
    f.statement = fact.statement,
```

### 5.4. Ảnh graph cần chèn

Chèn ảnh chụp từ Neo4j Browser hoặc Neo4j Bloom sau khi chạy:

```powershell
python manage.py sync_behavior_graph
```

Ảnh nên thể hiện:

- ít nhất các node `segment`, `category`, `service`, `policy`
- có nhiều cạnh liên kết
- layout rõ ràng, nhiều node sẽ có giá trị trình bày tốt hơn

Gợi ý caption:

- Hình 5. Knowledge Base Graph của hệ thống AI e-commerce.
- Hình 6. Truy vấn graph trong Neo4j theo segment người dùng.

---

## 6. Câu 2c - Xây dựng RAG và chat dựa trên KB_Graph

### 6.1. Ý tưởng

RAG được xây dựng theo hướng hybrid:

1. Dự đoán `behavior_segment` từ mô hình tốt nhất.
2. Dùng `GraphRetriever` truy vấn KB_Graph theo câu hỏi và segment.
3. Kết hợp kết quả graph với text knowledge base.
4. Tạo prompt và gửi cho LLM.
5. Trả lời lại cho user kèm sản phẩm gợi ý và giải thích.

Như vậy chatbot không chỉ trả lời hội thoại chung, mà còn trả lời dựa trên:

- hành vi mua sắm gần đây
- segment dự đoán
- tri thức trong graph
- nguồn ngữ cảnh truy xuất được

### 6.2. Code chính của câu 2c

File: [graph_retriever.py](../advisor-service/app/services/graph_retriever.py)

```python
def _segment_node_id(self, behavior_segment):
    if not behavior_segment:
        return None
    return f"segment:{behavior_segment.strip()}"
```

```python
def search(self, question, behavior_segment, top_k=5):
    graph = self._resolved_graph()
    question_tokens = self._tokenize(question)
    if not question_tokens and not behavior_segment:
        return {"facts": [], "paths": []}
```

File: [advisor.py](../advisor-service/app/services/advisor.py)

```python
def chat(self, user_id=None, question=""):
    books, profile, orders, reviews, cart_items = self._collect_behavior_inputs(user_id)
    features, prediction = self._predict_behavior(profile, books, orders, reviews, cart_items)
    behavior_segment = prediction["behavior_segment"]
    recommended_books = self._pick_books(books, behavior_segment)
    retrieval = self.rag_pipeline.retrieve(question, behavior_segment=behavior_segment, top_k=3)
```

### 6.3. Mô tả luồng xử lý

Khi user đặt câu hỏi, ví dụ: "Tôi muốn mua sách phù hợp với thói quen đọc của mình", hệ thống xử lý như sau:

1. Thu thập profile, order, review, cart.
2. Trích xuất chuỗi hành vi gần nhất.
3. Dùng `model_best` để dự đoán nhóm hành vi.
4. Truy vấn graph để lấy fact và path liên quan.
5. Kết hợp với text retrieval để sinh ngữ cảnh.
6. Tạo câu trả lời chat và trả về danh sách sách đề xuất.

### 6.4. Ảnh cần chèn

Chèn ảnh:

1. Màn hình chat hỏi đáp với user.
2. JSON/payload trả về có `behavior_segment`, `graph_facts`, `graph_paths`, `recommended_books`.

Gợi ý caption:

- Hình 7. Chatbot tư vấn sách dựa trên KB_Graph.
- Hình 8. Payload RAG trả về cho giao diện chat.

---

## 7. Câu 2d - Triển khai tích hợp trong hệ e-commerce

### 7.1. Mục tiêu tích hợp

Phần AI không dừng ở việc train mô hình, mà được tích hợp trực tiếp vào website bán sách:

- Khi khách hàng tìm kiếm sách, hệ thống hiển thị block recommendation.
- Khi khách hàng thêm vào giỏ hàng, hệ thống cập nhật gợi ý liên quan.
- Hệ thống có giao diện chat riêng trong website, không dùng giao diện mặc định của ChatGPT.

### 7.2. Thành phần giao diện đã tích hợp

Các file chính phía gateway:

- [views.py](../api-gateway/app/views.py)
- [books.html](../api-gateway/app/templates/books.html)
- [cart.html](../api-gateway/app/templates/cart.html)
- [advisor_panel.html](../api-gateway/app/templates/partials/advisor_panel.html)
- [base.html](../api-gateway/app/templates/base.html)

### 7.3. Chức năng tích hợp

1. `Books page`
   - Hiển thị danh sách sách.
   - Có shelf gợi ý theo hành vi người dùng.
2. `Cart page`
   - Hiển thị sản phẩm liên quan trong giỏ hàng.
   - Có gợi ý bổ sung dựa trên segment.
3. `Advisor panel`
   - Chat panel nổi theo phong cách bookstore.
   - Gọi `advisor-service` để nhận tư vấn.
   - Hiển thị câu trả lời và danh sách sách gợi ý.

### 7.4. Giá trị của phần tích hợp

- Tăng khả năng cá nhân hóa trải nghiệm mua sắm.
- Làm rõ vai trò thực tế của AI trong e-commerce.
- Thể hiện được kết nối hoàn chỉnh giữa dữ liệu, mô hình, graph, RAG và UI.

### 7.5. Ảnh cần chèn

Chèn ảnh:

1. Trang danh sách sách có recommendation shelf.
2. Trang giỏ hàng có gợi ý thêm.
3. Giao diện chat riêng của website.

Gợi ý caption:

- Hình 9. Recommendation shelf trên trang books.
- Hình 10. Gợi ý sản phẩm trên trang cart.
- Hình 11. Advisor chat panel trong hệ e-commerce.

---

## 8. Kết luận

Đề tài đã hoàn thành đầy đủ các yêu cầu:

1. Sinh dữ liệu `data_user500.csv` với 500 user và 8 hành vi.
2. Xây dựng và đánh giá 3 mô hình `RNN`, `LSTM`, `biLSTM`.
3. Lựa chọn được mô hình tốt nhất là `SimpleRNN`.
4. Xây dựng Knowledge Base Graph bằng Neo4j.
5. Xây dựng RAG và chatbot dựa trên KB_Graph.
6. Tích hợp thành công vào hệ e-commerce qua trang books, cart và giao diện chat.

Hệ thống thể hiện được một pipeline AI hoàn chỉnh từ dữ liệu đầu vào, học máy, lưu tri thức, truy xuất ngữ cảnh đến triển khai thực tế trong ứng dụng thương mại điện tử.

---

## 9. Phụ lục - Lệnh chạy

Tại thư mục `advisor-service`:

```powershell
python manage.py prepare_behavior_data
python manage.py train_behavior_model
python manage.py sync_behavior_graph
python manage.py test app.tests -v 2
```

Tại thư mục `api-gateway`:

```powershell
python manage.py test app.tests -v 2
```

## 10. Phụ lục - Kết quả kiểm thử

- `advisor-service`: `60 tests`, `OK`
- `api-gateway`: `41 tests`, `OK`

## 11. Ghi chú khi xuất PDF

- Đổi tên file thành đúng mẫu: `aiservice02_lớp.nhóm_tênho.PDF`
- Chèn ảnh plots, ảnh Neo4j và ảnh giao diện vào đúng các mục đã đánh dấu.
- Điền đầy đủ thông tin trang bìa trước khi xuất PDF.
