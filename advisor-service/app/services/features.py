from collections import Counter


PROFILE_FIELDS = ("age_group", "favorite_category", "price_sensitivity", "membership_tier")
SEQUENCE_LENGTH = 8
PURCHASE_ORDER_STATUSES = {"paid", "shipping", "delivered"}
SEQUENCE_BEHAVIORS = (
    "view_home",
    "search",
    "view_detail",
    "add_to_cart",
    "checkout",
    "review",
    "wishlist",
    "view_home",
)


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


def _normalize_text(value):
    return str(value or "").strip().lower()


def _normalize_profile_category(value):
    normalized = _normalize_text(value)
    if not normalized:
        return "general"
    if normalized in {"technology", "tech", "programming", "coding", "software", "data"}:
        return "technology"
    if normalized in {"literature", "fiction", "novel", "novels", "books", "reading"}:
        return "literature"
    if normalized in {"discounts", "deals", "savings"}:
        return "discounts"
    if normalized in {"business", "commerce"}:
        return "business"
    if normalized in {"children", "kids", "family", "story", "storybooks"}:
        return "general"
    return normalized.replace(" ", "_")


def _normalize_catalog_category(value):
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        numeric = int(value)
        if float(numeric) != float(value):
            return None
        return {
            3: "technology",
            5: "literature",
            7: "general",
            8: "business",
        }.get(numeric, "general")

    normalized = _normalize_text(value)
    if not normalized:
        return None

    mapping = {
        "technology": "technology",
        "programming": "technology",
        "software": "technology",
        "data": "technology",
        "literature": "literature",
        "fiction": "literature",
        "novel": "literature",
        "children": "general",
        "kids": "general",
        "family": "general",
        "business": "business",
        "discounts": "discounts",
        "deals": "discounts",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


def _normalize_price_band(value):
    normalized = _normalize_text(value)
    if normalized in {"low", "medium", "high"}:
        return normalized

    price = _safe_float(value, default=0.0)
    if price <= 0:
        return "medium"
    if price < 15:
        return "low"
    if price < 30:
        return "medium"
    return "high"


def _records_from_payload(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), (list, tuple)):
            return [item for item in payload.get("items", []) if isinstance(item, dict)]
        if isinstance(payload.get("results"), (list, tuple)):
            return [item for item in payload.get("results", []) if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, (list, tuple)):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _effective_orders(orders):
    valid_orders = _records_from_payload(orders)
    filtered = []
    for order in valid_orders:
        status = _normalize_text(order.get("status"))
        if status and status not in PURCHASE_ORDER_STATUSES:
            continue
        filtered.append(order)
    return filtered


def _lookup_book(book_by_id, book_id):
    if book_id in book_by_id:
        return book_by_id[book_id]
    string_key = str(book_id)
    if string_key in book_by_id:
        return book_by_id[string_key]
    try:
        int_key = int(book_id)
    except (TypeError, ValueError):
        return None
    return book_by_id.get(int_key)


def _book_category_and_price(book, default_category="general", default_price_band="medium"):
    if not isinstance(book, dict):
        return default_category, default_price_band
    category = _normalize_catalog_category(book.get("category")) or default_category
    price_band = _normalize_price_band(book.get("price")) or default_price_band
    return category, price_band


def _order_category_and_price(order, book_by_id, default_category="general", default_price_band="medium"):
    items = order.get("items") or []
    if not isinstance(items, (list, tuple)):
        items = []

    category_counter = Counter()
    item_prices = []
    total_quantity = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = max(_safe_int(item.get("quantity")), 0)
        total_quantity += quantity
        book = _lookup_book(book_by_id, item.get("book_id"))
        if not isinstance(book, dict):
            continue
        category, price_band = _book_category_and_price(book, default_category, default_price_band)
        category_counter[category] += max(quantity, 1)
        item_prices.append(_safe_float(book.get("price"), 0.0))

    if category_counter:
        category = category_counter.most_common(1)[0][0]
    else:
        category = default_category

    if item_prices:
        average_price = sum(item_prices) / len(item_prices)
    else:
        average_price = _safe_float(order.get("total_amount"), 0.0)

    return category, _normalize_price_band(average_price), total_quantity


def _review_category(reviews, book_by_id, default_category="general"):
    category_counter = Counter()
    for review in reviews:
        if not isinstance(review, dict):
            continue
        book = _lookup_book(book_by_id, review.get("book_id"))
        if not isinstance(book, dict):
            continue
        category, _ = _book_category_and_price(book, default_category)
        category_counter[category] += 1
    if category_counter:
        return category_counter.most_common(1)[0][0]
    return default_category


def _build_sequence_summary(source_counts, steps):
    return {
        "sequence_length": len(steps),
        "populated_steps": sum(1 for step in steps if step.get("behavior")),
        "source_counts": source_counts,
        "step_behaviors": [step.get("behavior", "") for step in steps],
        "step_categories": [step.get("category", "") for step in steps],
        "step_price_bands": [step.get("price_band", "") for step in steps],
    }


def _build_sequence_steps(profile, books, orders, reviews, cart_items):
    valid_books = _records_from_payload(books)
    valid_orders = _effective_orders(orders)
    valid_reviews = _records_from_payload(reviews)
    valid_cart_items = _records_from_payload(cart_items)

    book_by_id = {}
    for book in valid_books:
        book_id = book.get("id")
        if book_id is None:
            continue
        book_by_id[book_id] = book
        book_by_id[str(book_id)] = book

    profile_data = profile if isinstance(profile, dict) else {}
    preferred_category = _normalize_profile_category(profile_data.get("favorite_category"))
    profile_price_band = _normalize_price_band(profile_data.get("price_sensitivity"))

    dominant_catalog_category = preferred_category
    catalog_price_band = profile_price_band
    if valid_books:
        category_counter = Counter()
        price_bands = []
        for book in valid_books:
            category, price_band = _book_category_and_price(book, preferred_category, profile_price_band)
            category_counter[category] += 1
            price_bands.append(price_band)
        if category_counter:
            dominant_catalog_category = category_counter.most_common(1)[0][0]
        if price_bands:
            catalog_price_band = Counter(price_bands).most_common(1)[0][0]

    order_category = preferred_category
    order_price_band = profile_price_band
    order_quantity = 0
    if valid_orders:
        order_categories = Counter()
        order_price_bands = Counter()
        for order in valid_orders:
            category, price_band, quantity = _order_category_and_price(order, book_by_id, preferred_category, profile_price_band)
            order_categories[category] += 1
            order_price_bands[price_band] += 1
            order_quantity += quantity
        if order_categories:
            order_category = order_categories.most_common(1)[0][0]
        if order_price_bands:
            order_price_band = order_price_bands.most_common(1)[0][0]

    cart_category = preferred_category
    cart_price_band = profile_price_band
    if valid_cart_items:
        cart_categories = Counter()
        cart_price_bands = Counter()
        for item in valid_cart_items:
            book = _lookup_book(book_by_id, item.get("book_id"))
            if not isinstance(book, dict):
                continue
            category, price_band = _book_category_and_price(book, preferred_category, profile_price_band)
            cart_categories[category] += max(_safe_int(item.get("quantity")), 1)
            cart_price_bands[price_band] += 1
        if cart_categories:
            cart_category = cart_categories.most_common(1)[0][0]
        if cart_price_bands:
            cart_price_band = cart_price_bands.most_common(1)[0][0]

    review_category = _review_category(valid_reviews, book_by_id, preferred_category)

    steps = [
        {
            "behavior": "view_home",
            "category": preferred_category,
            "price_band": profile_price_band,
            "duration": 12,
            "source": "profile",
        },
        {
            "behavior": "search" if valid_orders else "view_detail",
            "category": order_category,
            "price_band": order_price_band,
            "duration": 16 if valid_orders else 11,
            "source": "orders",
        },
        {
            "behavior": "add_to_cart" if valid_cart_items else "wishlist",
            "category": cart_category,
            "price_band": cart_price_band,
            "duration": 10,
            "source": "cart_items",
        },
        {
            "behavior": "checkout" if valid_orders else "view_detail",
            "category": order_category,
            "price_band": order_price_band,
            "duration": 8,
            "source": "orders",
        },
        {
            "behavior": "review" if valid_reviews else "wishlist",
            "category": review_category,
            "price_band": "medium",
            "duration": 7,
            "source": "reviews",
        },
        {
            "behavior": "view_detail",
            "category": dominant_catalog_category,
            "price_band": catalog_price_band,
            "duration": 14,
            "source": "books",
        },
        {
            "behavior": "wishlist" if valid_cart_items or valid_reviews else "search",
            "category": cart_category if valid_cart_items else review_category,
            "price_band": cart_price_band if valid_cart_items else profile_price_band,
            "duration": 9,
            "source": "engagement",
        },
        {
            "behavior": "view_home",
            "category": preferred_category,
            "price_band": profile_price_band,
            "duration": 10,
            "source": "fallback",
        },
    ]

    source_counts = {
        "books": len(valid_books),
        "orders": len(valid_orders),
        "reviews": len(valid_reviews),
        "cart_items": len(valid_cart_items),
    }
    sequence_summary = _build_sequence_summary(source_counts, steps)
    sequence_summary["preferred_category"] = preferred_category
    sequence_summary["dominant_catalog_category"] = dominant_catalog_category
    sequence_summary["order_category"] = order_category
    sequence_summary["cart_category"] = cart_category
    sequence_summary["review_category"] = review_category
    sequence_summary["order_quantity"] = order_quantity

    features = {}
    for index, step in enumerate(steps, start=1):
        features[f"step_{index}_behavior"] = step["behavior"]
        features[f"step_{index}_category"] = step["category"]
        features[f"step_{index}_price_band"] = step["price_band"]
        features[f"step_{index}_duration"] = step["duration"]

    return features, sequence_summary


def build_behavior_features(profile, books, orders, reviews, cart_items):
    book_by_id = {}
    valid_books = _records_from_payload(books)
    for book in valid_books:
        book_id = book.get("id")
        if book_id is None:
            continue
        book_by_id[book_id] = book
        book_by_id[str(book_id)] = book

    category_counter = Counter()
    publisher_counter = Counter()
    total_spent = 0.0
    total_quantity = 0
    valid_orders = _effective_orders(orders)
    valid_reviews = _records_from_payload(reviews)
    valid_cart_items = _records_from_payload(cart_items)

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
            book = book_by_id.get(book_id) or book_by_id.get(str(book_id))
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

    sequence_features, sequence_summary = _build_sequence_steps(
        profile,
        valid_books,
        valid_orders,
        valid_reviews,
        valid_cart_items,
    )

    features = {
        "user_id": profile.get("id") if isinstance(profile, dict) else None,
        "age_group": str(profile.get("age_group", "")).strip() if isinstance(profile, dict) else "",
        "favorite_category": _normalize_profile_category(
            profile.get("favorite_category") if isinstance(profile, dict) else ""
        ),
        "price_sensitivity": _normalize_price_band(
            profile.get("price_sensitivity") if isinstance(profile, dict) else ""
        ),
        "membership_tier": _normalize_text(profile.get("membership_tier", "")) if isinstance(profile, dict) else "",
        "order_count": order_count,
        "total_spent": round(total_spent, 2),
        "average_order_value": round(total_spent / order_count, 2) if order_count else 0.0,
        "total_quantity": total_quantity,
        "review_count": len(valid_reviews),
        "average_review_rating": round(avg_rating, 2),
        "cart_item_count": len(valid_cart_items),
        "premium_interest_score": 1.0 if order_count and (total_spent / max(total_quantity, 1)) >= 18 else 0.0,
        "budget_interest_score": 1.0 if total_quantity and (total_spent / total_quantity) < 12 else 0.0,
        "sequence_summary": sequence_summary,
    }
    features.update(sequence_features)

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
