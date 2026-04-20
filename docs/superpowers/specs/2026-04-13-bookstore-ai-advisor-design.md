# Bookstore AI Advisor Design

## 1. Overview

This design adds an AI-powered customer behavior analysis and advisory capability to the existing `bookstore-microservice` project for an academic demo. The solution integrates directly into the current e-commerce architecture and demonstrates the required concepts:

- customer behavior analysis for service consultation
- a deep learning model named `model_behavior`
- a knowledge base for consultation
- Retrieval-Augmented Generation (RAG) for chat-based advice
- deployment and integration into the e-commerce system

The implementation target is a working end-to-end demo, not a production-grade recommendation platform. The system therefore prioritizes clarity, explainability, and successful integration over large-scale optimization.

## 2. Goals

- Integrate AI consultation into the existing bookstore microservice system.
- Classify each customer into a behavior segment using a deep learning model.
- Use that behavior segment to personalize book and service advice.
- Support natural-language consultation through a popup chat widget in the frontend.
- Ground chatbot answers in a local knowledge base and live bookstore data.
- Keep the architecture simple enough to deploy with the existing project setup.

## 3. Out of Scope

- Real-time event streaming between services
- a large-scale vector database
- online model retraining in production
- advanced ranking models for per-book personalized scoring
- fully local LLM inference
- high-availability or enterprise-scale deployment patterns

## 4. Recommended Architecture

### 4.1 New Service

Add a new microservice named `advisor-service`.

This service owns the AI advisory workflow and exposes internal APIs for:

- customer behavior profiling
- personalized consultation
- knowledge retrieval
- chat response generation

### 4.2 Existing Services Used as Data Sources

The new service reads or requests data from:

- `book-service` for books, categories, authors, publishers
- `cart-service` for active cart behavior
- `order-service` for purchase history
- `review-service` for rating and reviewing behavior
- `customer-service` or `user-service` for customer profile data
- `api-gateway` as the frontend integration point

### 4.3 Frontend Integration Point

`api-gateway` remains the user-facing web application and will be updated to:

- include a floating chat launcher in the shared base template
- open a popup chat widget on demand
- send chat requests to `advisor-service`
- show personalized answers and suggested books inside the popup

## 5. End-to-End Flow

1. A user opens the bookstore frontend in `api-gateway`.
2. The user clicks a floating chat button.
3. A popup chat widget opens at the bottom-right of the screen.
4. The user submits a question such as:
   - "Recommend books for me"
   - "What type of books should I read?"
   - "What is your shipping policy?"
5. `api-gateway` sends the request to `advisor-service`, including authenticated user information when available.
6. `advisor-service` aggregates customer behavior signals from the existing services.
7. `model_behavior` predicts the user's behavior segment.
8. The retrieval component fetches the most relevant KB documents and recommended book context.
9. The LLM API generates a final grounded answer.
10. The popup shows:
   - the advice message
   - recommended books
   - a short explanation linked to customer behavior

## 6. Behavior Analysis Design

### 6.1 Problem Framing

For this demo, `model_behavior` is a supervised deep learning classifier that predicts a customer behavior segment.

Recommended output labels:

- `tech_reader`
- `literature_reader`
- `family_reader`
- `bargain_hunter`
- `casual_buyer`

These labels are easy to explain during a presentation and are sufficient to drive personalized downstream advice.

### 6.2 Input Signals

Each customer will be represented by an aggregated feature vector built from available system data:

- order count
- total spending
- average order value
- purchase count by category
- review count
- average rating given
- cart activity count
- preference for low-price or high-price books
- author or publisher affinity counts
- recency of latest order or review

If some signals are not available or sparse, the pipeline will default them to zero so the demo stays robust.

### 6.3 Dataset Strategy

Because the project is an academic demo and likely has limited historical data, the training set will be created through a hybrid strategy:

- collect behavior records from the current services and seeded data
- derive an initial segment label using explicit heuristic rules
- convert those records into a structured training dataset
- train the classifier on that dataset

This keeps the workflow academically valid while remaining feasible in the current repository.

### 6.4 Model Choice

Use a simple Multi-Layer Perceptron (MLP) built with a deep learning library such as TensorFlow/Keras.

Recommended structure:

- input layer sized to the engineered feature vector
- 2 to 3 dense hidden layers with ReLU activation
- dropout for basic regularization
- softmax output over the behavior classes

This is enough to justify the use of deep learning without overcomplicating the implementation.

### 6.5 Inference Output

The inference service returns:

- `behavior_segment`
- probability scores per segment
- a human-readable explanation generated from top contributing behavior signals

This explanation is useful in both the chat response and the final demo presentation.

## 7. Knowledge Base Design

### 7.1 KB Purpose

The knowledge base supports service consultation and behavior-aware book advice.

It will contain information that the model alone cannot answer, such as:

- shopping and order policies
- payment and cancellation guidance
- shipping and notification guidance
- category descriptions
- audience suitability for book categories
- mappings from behavior segments to recommended reading styles

### 7.2 KB Document Types

The KB should be stored as small structured documents, for example JSON or YAML files, grouped into:

- `faq` documents
- `policy` documents
- `category` documents
- `segment_advice` documents
- `book_hint` documents

### 7.3 KB Metadata

Each document should include metadata to improve retrieval:

- `id`
- `title`
- `doc_type`
- `source_service`
- `category`
- `target_segment`
- `tags`

This metadata allows the retriever to combine semantic relevance with simple filtering rules.

## 8. RAG Chat Design

### 8.1 Retrieval Strategy

For the academic demo, use a lightweight retrieval approach:

- generate embeddings for KB documents
- store them in a small local vector index such as FAISS
- retrieve top-k documents for each user query
- optionally filter or boost by `target_segment`

If FAISS adds friction, a smaller fallback using cosine similarity over local embeddings is acceptable because the KB size will be limited.

### 8.2 Retrieved Context

The prompt context sent to the LLM should combine:

- user question
- predicted behavior segment
- short customer behavior explanation
- top KB documents
- a small list of candidate books from `book-service`

### 8.3 LLM Responsibilities

The external LLM API is responsible for generating the final answer, but only from grounded context provided by the advisor service.

The output should follow this structure:

- answer the user's question directly
- recommend 3 to 5 suitable books or categories when applicable
- explain why the recommendation matches the user's behavior
- mention relevant service policy details when the question asks about operations

### 8.4 Hallucination Control

To keep the demo defensible:

- do not let the model invent bookstore policies
- always prefer retrieved KB content for service-related answers
- if no supporting knowledge is found, respond conservatively
- clearly separate recommendation language from factual policy language

## 9. Frontend Popup Chat Design

### 9.1 Placement

The chat entry point is a floating circular or pill-shaped button visible across the bookstore UI.

Recommended placement:

- fixed to the bottom-right corner
- visible on all pages rendered from `api-gateway`

### 9.2 Popup Behavior

When the user clicks the launcher:

- a popup panel opens above the launcher
- the panel contains chat history, input, and send controls
- the panel can be minimized or closed
- the state persists while navigating within the current page session if feasible

### 9.3 Popup Content

The popup should include:

- a title such as "AI Book Advisor"
- a subtitle explaining that it can recommend books and answer service questions
- quick suggestion chips
- a scrollable message area
- a text input box
- a loading indicator during request processing

### 9.4 Personalization Rules

- If the user is logged in, include `user_id` or equivalent identity context for personalized advice.
- If the user is anonymous, allow general KB-based chat without personalized behavior inference.

### 9.5 Visual Direction

The current frontend already uses a modern dark glass style with blue and violet accents. The popup should match that visual language rather than introducing a separate design system.

## 10. Advisor Service Responsibilities

The `advisor-service` should be decomposed into focused modules:

- API layer for chat and profile endpoints
- data aggregation layer for fetching customer behavior data
- feature engineering layer for behavior vectors
- model inference layer for `model_behavior`
- knowledge base loader
- embedding and retrieval layer
- prompt builder
- LLM client wrapper

This keeps the new service understandable and testable.

## 11. API Design

Recommended internal endpoints:

- `POST /advisor/chat/`
  - input: user identity if available, user question
  - output: answer text, behavior segment, recommended books, supporting snippets
- `GET /advisor/profile/<user_id>/`
  - output: predicted behavior segment and explanation
- `POST /advisor/reindex/` optional for rebuilding KB embeddings in development

The popup chat primarily depends on `POST /advisor/chat/`.

## 12. Data and Asset Artifacts

Expected new assets:

- trained model artifact such as `model_behavior.h5`
- feature metadata or label mapping file
- KB source documents
- vector index files
- scripts for data preparation and training

These artifacts should live inside the new service in clearly named folders.

## 13. Error Handling

The system should fail gracefully in demo conditions:

- if customer history is missing, fall back to generic consultation
- if model inference fails, skip personalization and continue with KB-based answers
- if retrieval finds no relevant document, answer conservatively
- if the external LLM API fails, return a clear temporary-unavailable message

This is important because academic demos often run in unstable environments.

## 14. Testing Strategy

Testing should cover:

- behavior feature extraction from sample service responses
- model inference on known test vectors
- KB loading and retrieval correctness
- chat endpoint response shape
- popup chat request and render behavior in `api-gateway`

For the model itself, it is sufficient to verify that:

- the training pipeline runs
- the model file is generated
- inference returns one of the allowed labels

## 15. Deployment Strategy

### 15.1 Docker Compose

Update `docker-compose.yml` to add `advisor-service` and wire these environment variables:

- `ADVISOR_SERVICE_URL`
- external LLM API credentials
- existing internal service URLs needed by the advisor service

### 15.2 Render Deployment

Update `render.yaml` to:

- add a new private service for `advisor-service`
- provide required service-to-service URLs
- provide the external LLM API key and model name as environment variables
- expose `ADVISOR_SERVICE_URL` to `api-gateway`

## 16. Why This Design Fits the Assignment

This design directly satisfies the requested assignment parts:

- "Phan tich hanh vi khach hang de tu van dich vu"
  - handled by the behavior feature pipeline and personalized advisory flow
- "Xay dung mo hinh model_behavior dua tren Deep learning"
  - handled by the MLP classifier for customer segment prediction
- "xay dung KB cho tu van"
  - handled by the structured FAQ, policy, category, and segment documents
- "Ap dung RAG de xay dung chat tu van"
  - handled by retrieval over the KB plus grounded LLM generation
- "Deploy va tich hop trong He e-commerce"
  - handled through `advisor-service`, `api-gateway`, `docker-compose.yml`, and `render.yaml`

## 17. Implementation Boundaries

To keep this deliverable achievable in one repository cycle, the implementation should be limited to:

- one new `advisor-service`
- one trainable but lightweight `model_behavior`
- one small local KB
- one popup chat widget in `api-gateway`
- one integrated demo path from user question to grounded answer

Anything beyond this should only be added if time remains after the full end-to-end path is working.
