from collections import Counter

from .behavior_dataset import BehaviorDatasetSchema


def _safe_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_behavior_features(profile, books, orders, reviews, cart_items):
    book_by_id = {}
    for book in books or []:
        if not isinstance(book, dict):
            continue
        book_id = book.get("id")
        if book_id is None:
            continue
        book_by_id[book_id] = book

    category_counter = Counter()
    publisher_counter = Counter()
    total_spent = 0.0
    total_quantity = 0
    valid_orders = [order for order in orders or [] if isinstance(order, dict)]
    valid_reviews = [review for review in reviews or [] if isinstance(review, dict)]
    valid_cart_items = [item for item in cart_items or [] if isinstance(item, dict)]

    for order in valid_orders:
        total_spent += _safe_float(order.get("total_amount"))
        items = order.get("items") or []
        if not isinstance(items, (list, tuple)):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            book_id = item.get("book_id")
            if book_id is None:
                continue

            quantity = max(_safe_int(item.get("quantity")), 0)
            total_quantity += quantity
            book = book_by_id.get(book_id)
            if not isinstance(book, dict):
                continue

            category_id = book.get("category")
            if category_id is not None:
                category_counter[category_id] += quantity

            publisher_id = book.get("publisher")
            if publisher_id is not None:
                publisher_counter[publisher_id] += quantity

    review_ratings = [_safe_int(review.get("rating")) for review in valid_reviews]
    avg_rating = sum(review_ratings) / len(review_ratings) if review_ratings else 0.0
    order_count = len(valid_orders)

    features = {
        "user_id": profile.get("id") if isinstance(profile, dict) else None,
        "order_count": order_count,
        "total_spent": round(total_spent, 2),
        "average_order_value": round(total_spent / order_count, 2) if order_count else 0.0,
        "total_quantity": total_quantity,
        "review_count": len(valid_reviews),
        "average_review_rating": round(avg_rating, 2),
        "cart_item_count": len(valid_cart_items),
        "premium_interest_score": 1.0 if order_count and (total_spent / max(total_quantity, 1)) >= 18 else 0.0,
        "budget_interest_score": 1.0 if total_quantity and (total_spent / total_quantity) < 12 else 0.0,
    }

    for category_id, count in category_counter.items():
        features[f"category_{category_id}_count"] = count
    for publisher_id, count in publisher_counter.items():
        features[f"publisher_{publisher_id}_count"] = count

    return features


def infer_behavior_label(features):
    if features.get("budget_interest_score", 0) >= 1 and features.get("order_count", 0) >= 2:
        return "bargain_hunter"
    if features.get("category_3_count", 0) >= max(features.get("category_5_count", 0), 1) * 2:
        return "tech_reader"
    if features.get("category_5_count", 0) >= max(features.get("category_3_count", 0), 1) * 2:
        return "literature_reader"
    if features.get("category_8_count", 0) >= 2:
        return "family_reader"
    return "casual_buyer"


def build_behavior_dataset_schema(rows):
    return BehaviorDatasetSchema.from_rows(rows)


def vectorize_behavior_features(schema, features):
    return schema.vectorize_features(features)


def encode_behavior_label(schema, label):
    return schema.encode_label(label)


def export_behavior_dataset_metadata(schema):
    return schema.to_metadata()
