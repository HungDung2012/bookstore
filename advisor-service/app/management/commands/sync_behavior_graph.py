import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.services.clients import UpstreamClient
from app.services.graph_kb import GraphKnowledgeBase, Neo4jGraphService

APP_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = APP_DIR / "data" / "training" / "data_user500.csv"
GRAPH_DATA_DIR = APP_DIR / "data" / "knowledge_graph"


def _load_rows(dataset_path):
    if not dataset_path.exists():
        raise CommandError(f"Behavior dataset not found at {dataset_path}")

    with dataset_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


class Command(BaseCommand):
    help = "Regenerate the behavior graph artifacts and sync them to Neo4j."

    def handle(self, *args, **options):
        rows = _load_rows(DATASET_PATH)

        try:
            books = UpstreamClient().get_books()
        except Exception:
            books = []
            self.stdout.write(self.style.WARNING("Upstream book service unavailable; syncing dataset graph only."))

        neo4j_service = Neo4jGraphService.from_env()
        payload = neo4j_service.export_graph_data(rows, books)
        GraphKnowledgeBase.write_export_artifacts(GRAPH_DATA_DIR, payload)
        import_cypher_path = GRAPH_DATA_DIR / "import.cypher"
        import_cypher_path.write_text(neo4j_service.build_import_cypher(), encoding="utf-8")

        try:
            sync_result = neo4j_service.sync_graph_data(payload)
        except Exception as exc:
            sync_result = {"synced": False, "reason": f"Neo4j sync failed: {exc}"}

        if sync_result.get("synced"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Synced graph to Neo4j: nodes={sync_result.get('node_count', 0)} "
                    f"edges={sync_result.get('edge_count', 0)} facts={sync_result.get('fact_count', 0)}"
                )
            )
        else:
            self.stdout.write(self.style.WARNING(sync_result.get("reason", "Neo4j sync skipped.")))

        self.stdout.write(
            self.style.SUCCESS(
                f"Graph export regenerated at {GRAPH_DATA_DIR}: "
                f"nodes={payload['metadata']['node_count']} "
                f"edges={payload['metadata']['edge_count']} "
                f"facts={payload['metadata']['fact_count']}"
            )
        )
