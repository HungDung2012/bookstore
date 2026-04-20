import ast
from pathlib import Path

from django.test import SimpleTestCase


class DemoSeedCatalogTests(SimpleTestCase):
    def test_seed_data_contains_more_than_ten_books(self):
        seed_file = Path(__file__).resolve().parents[1] / "seed_data.py"
        module = ast.parse(seed_file.read_text(encoding="utf-8"))

        books_node = next(
            node.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "books" for target in node.targets)
        )

        self.assertGreater(len(books_node.elts), 10)
