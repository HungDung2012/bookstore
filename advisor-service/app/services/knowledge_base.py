import json
from pathlib import Path


class KnowledgeBaseService:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    def load_documents(self):
        documents = []
        if not self.base_path.exists():
            return documents

        for path in sorted(self.base_path.glob("*.json")):
            documents.extend(json.loads(path.read_text(encoding="utf-8")))
        return documents
