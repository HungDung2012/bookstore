# Bookstore UI, Role, and DDD Upgrade Design

## 1. Overview

This design upgrades the existing `bookstore-microservice` academic project in three directions:

- a more polished and modern web interface
- explicit role-based experiences for `admin`, `staff`, and `customer`
- domain decomposition at a DDD level suitable for coursework and reporting

The upgrade also expands the business flow so the demo can clearly show a complete e-commerce lifecycle:

- browsing products
- managing a cart
- creating an order
- completing payment
- tracking shipping

The target is still an academic demo. The design therefore favors clarity, coherent role separation, and end-to-end usability over a deep production-grade rearchitecture.

## 2. Goals

- Improve the frontend so it looks more intentional, modern, and presentation-ready.
- Separate the user experience by role: `admin`, `staff`, `customer`.
- Support a demo-ready business flow for `cart`, `order`, `payment`, and `shipping`.
- Increase the visible product catalog to more than 10 products.
- Introduce DDD decomposition at a conceptual and code-organization level that is easy to explain in a report.
- Preserve the existing microservice structure and build on the current AI advisor integration.

## 3. Out of Scope

- full event-driven DDD or CQRS
- distributed transactions beyond the current academic flow
- a complete rewrite of every service into strict layered architecture
- external payment gateway integration
- real shipping provider integration
- advanced access-control infrastructure beyond role-based routing and view protection

## 4. Recommended Approach

Keep the current microservice architecture and upgrade it incrementally:

- improve `api-gateway` to provide a cleaner visual system and separate entry points by role
- make `user-service` roles explicit and stable: `admin`, `staff`, `customer`
- complete the customer buying flow through `cart`, `order`, `payment`, and `shipping`
- add a lightweight `shipping-service` so shipping becomes a visible bounded context
- align the codebase and report with DDD concepts without forcing a risky full rewrite

This keeps the implementation achievable while making the system much easier to present to the instructor.

## 5. Role Model

### 5.1 Admin

`admin` is responsible for system oversight and catalog administration.

Primary responsibilities:

- manage users and their roles
- manage products, categories, and publishers
- observe inventory at a high level
- access an admin dashboard with system summary cards

### 5.2 Staff

`staff` is responsible for operational fulfillment after the customer places an order.

Primary responsibilities:

- review incoming orders
- update order handling progress
- create and update shipment records
- change shipping status through a simple workflow:
  - `pending`
  - `packed`
  - `shipping`
  - `delivered`

### 5.3 Customer

`customer` is the buyer-facing role.

Primary responsibilities:

- browse products
- view product details
- add items to cart
- checkout and submit an order
- choose a payment option
- view order history and shipping status
- access the AI advisor popup for consultation

## 6. User Experience Design

### 6.1 Shared Design Direction

The upgraded UI should feel cleaner and more deliberate than the current screens:

- stronger visual hierarchy
- more polished cards, buttons, spacing, and typography
- consistent layout shell with header, role-aware navigation, and content panels
- responsive behavior for desktop and mobile

The frontend should still be template-based and pragmatic. The goal is not a visual redesign for its own sake, but a system that makes the product look complete and easier to demo.

### 6.2 Customer Screens

Customer-facing screens:

- improved catalog landing page
- product detail page
- cart page
- checkout page
- payment result page
- "My Orders" page
- shipping tracking page
- AI advisor popup preserved across customer pages

The customer flow should be easy to narrate from discovery to fulfillment.

### 6.3 Staff Screens

Staff-facing screens:

- operations dashboard
- order list needing processing
- order detail/update page
- shipping management page

The staff UI should prioritize speed and clarity over decoration.

### 6.4 Admin Screens

Admin-facing screens:

- admin dashboard
- user and role management page
- product management page
- category/publisher maintenance page
- inventory summary view

The admin UI should make it obvious that this role controls the catalog and users rather than order fulfillment.

## 7. Business Flow

### 7.1 Catalog and Cart

1. Customer browses products from `book-service`.
2. Customer adds products to `cart-service`.
3. Cart stores user-specific line items and quantities.

### 7.2 Order Creation

1. Customer confirms checkout.
2. `api-gateway` submits the purchase to `order-service`.
3. `order-service` creates an order and order items from the cart snapshot.
4. Cart can then be cleared or marked as converted.

### 7.3 Payment

1. Customer selects a demo payment option.
2. `payment-service` records a payment attempt.
3. Successful payment updates the order to a paid state.

For the academic demo, payment may be simulated through deterministic success and failure options rather than a real gateway.

### 7.4 Shipping

1. After an order exists, a shipment record is created in `shipping-service`.
2. `staff` updates shipping status as the order progresses.
3. `customer` views the latest shipping state from the frontend.

This gives the demo a complete end-to-end post-purchase lifecycle.

## 8. DDD Decomposition

The project only needs DDD at level 1, so the primary goal is to make domain boundaries explicit and defensible.

### 8.1 Bounded Contexts

- `Identity Context`
  - users, authentication, roles
- `Catalog Context`
  - books/products, categories, publishers
- `Cart Context`
  - shopping cart and line items
- `Ordering Context`
  - orders and order items
- `Payment Context`
  - payment attempts and payment status
- `Shipping Context`
  - shipment and shipping status
- `Advisory Context`
  - behavior analysis, AI consultation, knowledge retrieval

### 8.2 Context-to-Service Mapping

- `user-service` -> `Identity Context`
- `book-service` -> `Catalog Context`
- `cart-service` -> `Cart Context`
- `order-service` -> `Ordering Context`
- `payment-service` -> `Payment Context`
- new `shipping-service` -> `Shipping Context`
- `advisor-service` -> `Advisory Context`
- `api-gateway` -> presentation and orchestration layer

### 8.3 DDD Concepts to Surface in Code and Report

The report and code should explicitly identify:

- key entities per context
- responsibilities owned by each service
- application workflows spanning multiple contexts
- boundaries between domain logic and presentation logic

This is sufficient for academic DDD decomposition without introducing unnecessary architectural complexity.

## 9. Service-Level Changes

### 9.1 API Gateway

Upgrade `api-gateway` to:

- route users to role-specific dashboards after login
- render role-aware navigation
- improve layout and styling
- integrate pages for cart, checkout, order history, and shipping tracking
- keep the AI advisor popup available for customers

### 9.2 User Service

Upgrade `user-service` to:

- ensure roles are first-class and consistent
- support `admin`, `staff`, `customer`
- expose role information to the gateway after authentication

### 9.3 Book Service

Upgrade `book-service` to:

- seed more than 10 products
- support cleaner catalog and product detail rendering
- remain the source of truth for product information

### 9.4 Cart Service

Upgrade `cart-service` to:

- support standard customer cart interactions
- keep cart entries associated with the authenticated customer

### 9.5 Order Service

Upgrade `order-service` to:

- create orders from cart contents
- store an order lifecycle suitable for demo states such as:
  - `pending`
  - `paid`
  - `processing`
  - `completed`

### 9.6 Payment Service

Upgrade `payment-service` to:

- record a payment transaction for a selected order
- return a simple success/failure result for the academic demo

### 9.7 Shipping Service

Add a lightweight `shipping-service`.

Responsibilities:

- create shipment records for orders
- allow staff to update shipment status
- expose shipping status to customers through the gateway

This service is recommended because it makes the DDD story much clearer than burying shipping inside `order-service`.

## 10. Data and Demo Content

To support a better demo:

- seed more than 10 products with varied categories and publishers
- create at least one account for each role
- prepare sample orders and shipment states if necessary

Suggested demo users:

- `admin`
- `staff`
- `customer`

This helps the instructor quickly verify role separation during the presentation.

## 11. Security and Access Rules

The upgraded system should enforce simple role-based rules:

- only `admin` can manage users and products
- only `staff` can process orders and update shipping
- only `customer` can manage their own cart and view their own orders

For the academic scope, gateway-level access control plus service-level ownership checks is sufficient.

## 12. Error Handling

The system should gracefully handle:

- unauthenticated access to protected views
- users attempting to access pages outside their role
- payment failures
- missing shipment records
- unavailable internal services

The frontend should render user-friendly messages rather than raw backend failures.

## 13. Testing Strategy

Verification should focus on the main academic requirements:

- role-based routing and page protection
- customer cart and checkout flow
- payment success/failure behavior
- staff shipping updates
- customer shipping visibility
- basic admin product/user management flow
- unchanged advisor integration for customer-facing pages

Tests do not need to be exhaustive, but they should prove the main flows work.

## 14. Deployment Impact

Deployment changes:

- add `shipping-service` to `docker-compose.yml`
- add `shipping-service` to `render.yaml`
- update gateway environment variables and routing as needed

The existing AI advisor deployment remains part of the full stack.

## 15. Implementation Sequence

Recommended order of execution:

1. stabilize role model and routing
2. upgrade the frontend layout and shared styling
3. add role-specific dashboards
4. complete customer cart/order/payment flow
5. add shipping-service and staff shipping workflow
6. expand seed/demo data
7. align documentation and code references with DDD bounded contexts

This sequence reduces integration risk while keeping the demo visible at each stage.

## 16. Success Criteria

The upgrade is successful when:

- the UI is visibly more polished than the current version
- users are separated into `admin`, `staff`, and `customer`
- each role has dedicated pages and responsibilities
- the product catalog contains more than 10 products
- the demo can show `cart -> order -> payment -> shipping`
- the system can be explained in terms of clear DDD bounded contexts
- the existing AI advisor still works for the customer-facing experience
