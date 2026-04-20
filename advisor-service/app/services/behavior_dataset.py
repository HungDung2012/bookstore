from dataclasses import dataclass
import random
from typing import Iterable

EXCLUDED_COLUMNS = {"label", "user_id"}
SEQUENCE_PROFILE_FIELDS = [
    "user_id",
    "age_group",
    "favorite_category",
    "price_sensitivity",
    "membership_tier",
]
SEQUENCE_LABELS = (
    "impulse_buyer",
    "careful_researcher",
    "discount_hunter",
    "loyal_reader",
    "window_shopper",
)
SEQUENCE_STEP_COMPONENTS = ("behavior", "category", "price_band", "duration")
SEQUENCE_BEHAVIOR_VOCAB = (
    "view_home",
    "search",
    "view_detail",
    "add_to_cart",
    "remove_from_cart",
    "wishlist",
    "checkout",
    "review",
)
SEQUENCE_BEHAVIOR_PATTERNS = {
    "impulse_buyer": (
        (
            "view_home",
            "add_to_cart",
            "checkout",
            "review",
            "view_detail",
            "wishlist",
            "search",
            "remove_from_cart",
        ),
        (
            "search",
            "view_home",
            "add_to_cart",
            "checkout",
            "view_detail",
            "wishlist",
            "review",
            "remove_from_cart",
        ),
        (
            "view_home",
            "view_detail",
            "add_to_cart",
            "checkout",
            "wishlist",
            "search",
            "review",
            "remove_from_cart",
        ),
    ),
    "careful_researcher": (
        (
            "search",
            "view_detail",
            "search",
            "wishlist",
            "view_detail",
            "search",
            "review",
            "view_detail",
        ),
        (
            "view_detail",
            "search",
            "wishlist",
            "search",
            "view_detail",
            "review",
            "search",
            "wishlist",
        ),
        (
            "search",
            "search",
            "view_detail",
            "wishlist",
            "review",
            "view_detail",
            "search",
            "checkout",
        ),
    ),
    "discount_hunter": (
        (
            "search",
            "view_home",
            "add_to_cart",
            "remove_from_cart",
            "wishlist",
            "checkout",
            "search",
            "review",
        ),
        (
            "view_home",
            "search",
            "wishlist",
            "add_to_cart",
            "checkout",
            "remove_from_cart",
            "review",
            "search",
        ),
        (
            "search",
            "add_to_cart",
            "view_home",
            "wishlist",
            "remove_from_cart",
            "checkout",
            "search",
            "review",
        ),
    ),
    "loyal_reader": (
        (
            "view_home",
            "view_detail",
            "wishlist",
            "review",
            "view_detail",
            "view_home",
            "checkout",
            "review",
        ),
        (
            "view_detail",
            "view_home",
            "wishlist",
            "review",
            "checkout",
            "view_detail",
            "view_home",
            "review",
        ),
        (
            "view_home",
            "wishlist",
            "view_detail",
            "review",
            "view_detail",
            "checkout",
            "view_home",
            "review",
        ),
    ),
    "window_shopper": (
        (
            "view_home",
            "search",
            "view_detail",
            "wishlist",
            "remove_from_cart",
            "view_home",
            "search",
            "view_detail",
        ),
        (
            "search",
            "view_home",
            "wishlist",
            "view_detail",
            "remove_from_cart",
            "search",
            "view_home",
            "wishlist",
        ),
        (
            "view_home",
            "view_detail",
            "search",
            "wishlist",
            "view_home",
            "remove_from_cart",
            "search",
            "view_detail",
        ),
    ),
}
SEQUENCE_STEP_FIELDS = [
    *[f"step_{step_index}_behavior" for step_index in range(1, 9)],
    *[f"step_{step_index}_category" for step_index in range(1, 9)],
    *[f"step_{step_index}_price_band" for step_index in range(1, 9)],
    *[f"step_{step_index}_duration" for step_index in range(1, 9)],
]
SEQUENCE_PROFILE_CHOICES = {
    "age_group": ("18-25", "26-35", "36-45", "46-55", "55+"),
    "favorite_category": ("technology", "literature", "discounts", "business", "general"),
    "price_sensitivity": ("low", "medium", "high"),
    "membership_tier": ("bronze", "silver", "gold", "platinum"),
}
SEQUENCE_STEP_POOLS = {
    "impulse_buyer": (
        ("browse", "tap", "discover"),
        ("electronics", "novelty", "general"),
        ("low", "mid", "high"),
        ("6", "8", "12"),
        ("add_to_cart", "scroll", "search"),
        ("electronics", "general", "deals"),
        ("mid", "high", "low"),
        ("5", "9", "14"),
        ("checkout", "compare", "browse"),
        ("general", "electronics", "books"),
        ("high", "mid", "low"),
        ("7", "10", "16"),
        ("review", "share", "wishlist"),
        ("general", "books", "electronics"),
        ("mid", "high", "low"),
        ("4", "6", "11"),
        ("repeat_visit", "recommendation", "browse"),
        ("electronics", "general", "books"),
        ("low", "mid", "high"),
        ("8", "12", "17"),
        ("share", "wishlist", "browse"),
        ("general", "electronics", "books"),
        ("mid", "high", "low"),
        ("6", "9", "13"),
        ("purchase", "checkout", "cart"),
        ("electronics", "general", "books"),
        ("high", "mid", "low"),
        ("5", "8", "15"),
        ("return_visit", "browse", "recommendation"),
        ("general", "electronics", "books"),
        ("low", "mid", "high"),
        ("3", "7", "10"),
    ),
    "careful_researcher": (
        ("search", "browse", "compare"),
        ("literature", "business", "technology"),
        ("low", "medium", "high"),
        ("10", "14", "18"),
        ("read_excerpt", "compare", "search"),
        ("literature", "general", "technology"),
        ("medium", "low", "high"),
        ("8", "12", "16"),
        ("compare", "wishlist", "search"),
        ("literature", "business", "general"),
        ("low", "medium", "high"),
        ("9", "13", "17"),
        ("wishlist", "review", "save"),
        ("literature", "technology", "general"),
        ("medium", "low", "high"),
        ("7", "11", "15"),
        ("cart", "search", "browse"),
        ("literature", "business", "technology"),
        ("low", "medium", "high"),
        ("6", "10", "14"),
        ("checkout", "compare", "browse"),
        ("literature", "general", "business"),
        ("medium", "high", "low"),
        ("8", "12", "18"),
        ("review", "share", "highlight"),
        ("literature", "technology", "general"),
        ("low", "medium", "high"),
        ("5", "9", "13"),
        ("repeat_visit", "browse", "search"),
        ("literature", "general", "books"),
        ("medium", "low", "high"),
        ("6", "11", "14"),
    ),
    "discount_hunter": (
        ("browse", "search", "deal"),
        ("discounts", "general", "electronics"),
        ("high", "mid", "low"),
        ("4", "6", "9"),
        ("filter", "sort", "browse"),
        ("discounts", "books", "general"),
        ("high", "mid", "low"),
        ("5", "7", "12"),
        ("compare", "deal", "wishlist"),
        ("discounts", "electronics", "general"),
        ("low", "mid", "high"),
        ("6", "8", "11"),
        ("add_to_cart", "coupon", "browse"),
        ("discounts", "general", "books"),
        ("high", "mid", "low"),
        ("4", "9", "13"),
        ("checkout", "coupon", "cart"),
        ("discounts", "books", "electronics"),
        ("mid", "high", "low"),
        ("3", "7", "10"),
        ("review", "share", "browse"),
        ("general", "discounts", "books"),
        ("high", "mid", "low"),
        ("5", "8", "12"),
        ("repeat_visit", "deal", "browse"),
        ("discounts", "general", "electronics"),
        ("low", "mid", "high"),
        ("4", "6", "10"),
        ("wishlist", "search", "browse"),
        ("general", "discounts", "books"),
        ("high", "mid", "low"),
        ("3", "5", "9"),
    ),
    "loyal_reader": (
        ("browse", "search", "read"),
        ("literature", "general", "technology"),
        ("medium", "low", "high"),
        ("8", "12", "15"),
        ("review", "compare", "save"),
        ("literature", "books", "general"),
        ("low", "medium", "high"),
        ("7", "10", "13"),
        ("wishlist", "browse", "search"),
        ("literature", "general", "books"),
        ("medium", "low", "high"),
        ("9", "11", "14"),
        ("cart", "review", "browse"),
        ("literature", "books", "general"),
        ("low", "medium", "high"),
        ("6", "9", "12"),
        ("checkout", "cart", "browse"),
        ("literature", "general", "technology"),
        ("medium", "low", "high"),
        ("5", "8", "11"),
        ("review", "share", "highlight"),
        ("literature", "books", "general"),
        ("low", "medium", "high"),
        ("4", "7", "10"),
        ("repeat_visit", "browse", "recommendation"),
        ("literature", "general", "books"),
        ("medium", "low", "high"),
        ("5", "8", "12"),
        ("share", "browse", "wishlist"),
        ("literature", "books", "general"),
        ("low", "medium", "high"),
        ("3", "6", "9"),
    ),
    "window_shopper": (
        ("browse", "search", "window"),
        ("general", "books", "electronics"),
        ("high", "mid", "low"),
        ("3", "5", "7"),
        ("compare", "browse", "search"),
        ("general", "books", "discounts"),
        ("high", "mid", "low"),
        ("4", "6", "9"),
        ("wishlist", "save", "browse"),
        ("general", "electronics", "books"),
        ("mid", "high", "low"),
        ("5", "8", "10"),
        ("cart", "browse", "compare"),
        ("general", "books", "technology"),
        ("high", "mid", "low"),
        ("4", "7", "11"),
        ("checkout", "cart", "browse"),
        ("general", "electronics", "books"),
        ("mid", "high", "low"),
        ("3", "6", "8"),
        ("review", "share", "browse"),
        ("general", "books", "discounts"),
        ("high", "mid", "low"),
        ("4", "7", "10"),
        ("repeat_visit", "browse", "search"),
        ("general", "electronics", "books"),
        ("mid", "high", "low"),
        ("3", "5", "9"),
        ("return_visit", "window", "browse"),
        ("general", "books", "technology"),
        ("high", "mid", "low"),
        ("4", "6", "8"),
    ),
}


def _coerce_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BehaviorDatasetSchema:
    feature_names: list[str]
    labels: list[str]

    @classmethod
    def from_rows(cls, rows: Iterable[dict]):
        rows = [row for row in rows if isinstance(row, dict)]
        feature_names = sorted(
            {
                key
                for row in rows
                for key in row.keys()
                if key not in EXCLUDED_COLUMNS
            }
        )
        labels = sorted(
            {
                str(row["label"]).strip()
                for row in rows
                if row.get("label") not in (None, "")
            }
        )
        return cls(feature_names=feature_names, labels=labels)

    @property
    def export_fieldnames(self):
        return [*self.feature_names, "label"]

    def vectorize_features(self, features):
        feature_map = features if isinstance(features, dict) else {}
        return [_coerce_float(feature_map.get(name, 0.0)) for name in self.feature_names]

    def build_record(self, features, label):
        feature_map = features if isinstance(features, dict) else {}
        record = {
            name: _coerce_float(feature_map.get(name, 0.0))
            for name in self.feature_names
        }
        record["label"] = str(label).strip()
        return record

    def encode_label(self, label):
        label_value = str(label).strip()
        try:
            return self.labels.index(label_value)
        except ValueError as exc:
            raise ValueError(f"Unknown label: {label_value}") from exc

    def to_metadata(self):
        return {
            "feature_names": list(self.feature_names),
            "labels": list(self.labels),
            "feature_count": len(self.feature_names),
            "label_count": len(self.labels),
        }


@dataclass(frozen=True)
class BehaviorSequenceSchema:
    profile_fields: list[str]
    step_fields: list[str]
    labels: list[str]

    @classmethod
    def from_rows(cls, rows: Iterable[dict]):
        rows = [row for row in rows if isinstance(row, dict)]
        return cls(
            profile_fields=list(SEQUENCE_PROFILE_FIELDS),
            step_fields=list(SEQUENCE_STEP_FIELDS),
            labels=list(SEQUENCE_LABELS),
        )

    @property
    def export_fieldnames(self):
        return [*self.profile_fields, *self.step_fields, "label"]

    def build_record(self, sequence, label):
        sequence_map = sequence if isinstance(sequence, dict) else {}
        record = {name: sequence_map.get(name, "") for name in self.profile_fields}
        for name in self.step_fields:
            record[name] = sequence_map.get(name, "")
        record["label"] = str(label).strip()
        return record

    def encode_label(self, label):
        label_value = str(label).strip()
        try:
            return self.labels.index(label_value)
        except ValueError as exc:
            raise ValueError(f"Unknown label: {label_value}") from exc

    def to_metadata(self):
        return {
            "profile_fields": list(self.profile_fields),
            "step_fields": list(self.step_fields),
            "label_family": list(self.labels),
            "profile_field_count": len(self.profile_fields),
            "step_field_count": len(self.step_fields),
            "sequence_length": len(self.step_fields) // len(SEQUENCE_STEP_COMPONENTS),
            "label_count": len(self.labels),
            "column_count": len(self.export_fieldnames),
        }


def _pick_sequence_step(label, step_index, component_index, rng, variant_index=0):
    if component_index == 0:
        return SEQUENCE_BEHAVIOR_PATTERNS[label][variant_index % len(SEQUENCE_BEHAVIOR_PATTERNS[label])][step_index]
    pools = SEQUENCE_STEP_POOLS[label]
    pool_index = (step_index * len(SEQUENCE_STEP_COMPONENTS) + component_index + variant_index) % len(pools)
    options = pools[pool_index]
    return rng.choice(options)


def _pick_profile_value(field_name, rng):
    return rng.choice(SEQUENCE_PROFILE_CHOICES[field_name])


def generate_behavior_sequence_rows(user_count=500, step_count=8, seed=500):
    plan_rng = random.Random(seed)
    rng = random.Random(seed + 1)
    rows = []
    label_plan = list(SEQUENCE_LABELS) * (user_count // len(SEQUENCE_LABELS))
    label_plan.extend(list(SEQUENCE_LABELS)[: user_count % len(SEQUENCE_LABELS)])
    plan_rng.shuffle(label_plan)
    label_occurrences = {label: 0 for label in SEQUENCE_LABELS}
    for user_id, label in enumerate(label_plan, start=1):
        variant_index = label_occurrences[label] % len(SEQUENCE_BEHAVIOR_PATTERNS[label])
        label_occurrences[label] += 1
        row = {
            "user_id": user_id,
            "age_group": _pick_profile_value("age_group", rng),
            "favorite_category": _pick_profile_value("favorite_category", rng),
            "price_sensitivity": _pick_profile_value("price_sensitivity", rng),
            "membership_tier": _pick_profile_value("membership_tier", rng),
            "label": label,
        }
        for step_index in range(step_count):
            for component_index, component in enumerate(SEQUENCE_STEP_COMPONENTS):
                field_name = f"step_{step_index + 1}_{component}"
                if component == "duration":
                    row[field_name] = rng.randint(3, 18)
                else:
                    row[field_name] = _pick_sequence_step(label, step_index, component_index, rng, variant_index)
        rows.append(row)
    return rows
