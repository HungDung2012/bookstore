from collections import Counter


def build_behavior_features(profile, books, orders, reviews, cart_items):
    book_by_id = {book["id"]: book for book in books}
    category_counter = Counter()
    publisher_counter = Counter()
    total_spent = 0.0
    total_quantity = 0

    for order in orders:
        total_spent += float(order.get("total_amount", 0) or 0)
        for item in order.get("items", []):
            quantity = int(item.get("quantity", 0) or 0)
            total_quantity += quantity
            book = book_by_id.get(item["book_id"], {})
            if book.get("category"):
                category_counter[book["category"]] += quantity
            if book.get("publisher"):
                publisher_counter[book["publisher"]] += quantity

    review_ratings = [int(review.get("rating", 0) or 0) for review in reviews]
    avg_rating = sum(review_ratings) / len(review_ratings) if review_ratings else 0.0

    features = {
        "user_id": profile.get("id"),
        "order_count": len(orders),
        "total_spent": round(total_spent, 2),
        "average_order_value": round(total_spent / len(orders), 2) if orders else 0.0,
        "total_quantity": total_quantity,
        "review_count": len(reviews),
        "average_review_rating": round(avg_rating, 2),
        "cart_item_count": len(cart_items),
        "premium_interest_score": 1.0 if orders and (total_spent / max(total_quantity, 1)) >= 18 else 0.0,
        "budget_interest_score": 1.0 if total_quantity and (total_spent / total_quantity) < 12 else 0.0,
    }

    for category_id, count in category_counter.items():
        features[f"category_{category_id}_count"] = count
    for publisher_id, count in publisher_counter.items():
        features[f"publisher_{publisher_id}_count"] = count

    return features
