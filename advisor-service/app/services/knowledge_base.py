import json
from pathlib import Path


class KnowledgeBaseService:
    _APP_ROOT = Path(__file__).resolve().parents[2]

    def __init__(self, base_path):
        base_path = Path(base_path)
        self.base_path = base_path if base_path.is_absolute() else self._APP_ROOT / base_path

    def load_documents(self):
        documents = []
        if not self.base_path.exists():
            return documents

        for path in sorted(self.base_path.glob("*.json")):
            documents.extend(json.loads(path.read_text(encoding="utf-8")))
        return documents
