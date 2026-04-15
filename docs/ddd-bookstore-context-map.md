# Bookstore DDD Context Map

Tai lieu nay dung muc DDD level 1 cho du an `bookstore-microservice`. Muc tieu la lam ro ranh gioi domain, khong refactor sang CQRS/event-driven.

## 1. Bounded Contexts

| Context | Key entities / aggregates | Major responsibilities | Main roles |
| --- | --- | --- | --- |
| Identity | `User`, `Role`, `Session` | Xac thuc, phan quyen, quan ly tai khoan | `admin`, `staff`, `customer` |
| Catalog | `Book`, `Category`, `Publisher` | Quan ly san pham, danh muc, thong tin mo ta | `admin`, `customer` |
| Ordering | `Cart`, `CartItem`, `Order`, `OrderItem` | Gio hang, tao don, trang thai don | `customer`, `staff` |
| Payment | `Payment`, `PaymentAttempt` | Tao giao dich, ghi nhan trang thai thanh toan | `customer`, `staff` |
| Shipping | `Shipment`, `ShippingEvent` | Tao van don, cap nhat trang thai giao hang | `staff`, `customer` |
| Advisory | `BehaviorProfile`, `KnowledgeDoc`, `Recommendation` | Phan tich hanh vi, RAG, tu van sach/dich vu | `customer`, `admin` |

## 2. Microservice Mapping

| Microservice | Bounded context | Notes |
| --- | --- | --- |
| `user-service` | Identity | Quan ly nguoi dung va role `admin/staff/customer` |
| `book-service` | Catalog | Nguon du lieu san pham, category, publisher |
| `cart-service` | Ordering | Luu cart cua customer dang dang nhap |
| `order-service` | Ordering | Tao va cap nhat order tu cart / checkout |
| `payment-service` | Payment | Demo thanh toan va cap nhat trang thai don |
| `shipping-service` | Shipping | Quan ly shipment va tracking |
| `advisor-service` | Advisory | Model behavior, KB, RAG chat tu van |
| `api-gateway` | Presentation / orchestration | Dieu huong role, render UI, proxy request |

## 3. Why This Is DDD Level 1

- Moi bounded context co mot trach nhiem ro rang va duoc gan voi mot microservice chinh.
- `admin` tap trung catalog va user management.
- `staff` tap trung order processing va shipping.
- `customer` tap trung browse -> cart -> checkout -> payment -> tracking.
- Tich hop giua context chu yeu qua `api-gateway`, phu hop cho demo hoc thuat va bao cao.

## 4. Report Summary

To chuc nay giup he thong bookstore duoc chia theo nghiep vu:

- Identity: ai dang nhap va quyen gi
- Catalog: ban cai gi
- Ordering: mua nhu the nao
- Payment: tra tien ra sao
- Shipping: giao hang nhu the nao
- Advisory: AI tu van gi cho customer

Day la muc phan ranh du lieu va trach nhiem du la de trinh bay DDD level 1 trong bao cao mon hoc.
