from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coral_portfolio.store import LocalStore
from coral_portfolio.workflow import (
    Provider,
    assemble_context,
    effective_disclosure,
    run_workflow,
    select_provider,
)


PROVIDERS = (
    Provider("local-demo", "local-placeholder", "local"),
    Provider("cloud-demo", "cloud-placeholder", "remote"),
)


class WorkflowTests(unittest.TestCase):
    def test_context_is_bounded(self) -> None:
        result = assemble_context("Synthetic request", ["Synthetic note " * 20], 80)
        self.assertLessEqual(len(result), 80)
        self.assertTrue(result.startswith("User request:"))

    def test_unknown_disclosure_fails_closed(self) -> None:
        self.assertEqual(effective_disclosure(["cloud_allowed", "unclassified"]), "local_only")
        self.assertEqual(effective_disclosure([]), "local_only")

    def test_local_only_never_selects_remote_provider(self) -> None:
        provider, reason = select_provider("local_only", "remote", PROVIDERS)
        self.assertEqual(provider.locality, "local")
        self.assertEqual(reason, "local fallback")

    def test_cloud_allowed_can_select_preferred_remote_provider(self) -> None:
        provider, reason = select_provider("cloud_allowed", "remote", PROVIDERS)
        self.assertEqual(provider.locality, "remote")
        self.assertEqual(reason, "preferred eligible provider")

    def test_workflow_persists_metadata_only_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with LocalStore(Path(temp_dir) / "demo.sqlite") as store:
                memory_id = store.add_memory(
                    "synthetic-1", "Synthetic project review happens on Thursday.", "cloud_allowed"
                )
                result = run_workflow(
                    store,
                    user_message="When is the synthetic review?",
                    memory_id=memory_id,
                    user_disclosure="local_only",
                    preferred_locality="remote",
                    budget_chars=300,
                    providers=PROVIDERS,
                )
                self.assertEqual(result.locality, "local")
                self.assertEqual(result.disclosure, "local_only")
                self.assertEqual(store.receipt_count(), 1)
                receipt = store.connection.execute(
                    "SELECT * FROM operation_receipts"
                ).fetchone()
                self.assertNotIn("Synthetic project review", str(dict(receipt)))
                self.assertNotIn("When is the synthetic review", str(dict(receipt)))


if __name__ == "__main__":
    unittest.main()
