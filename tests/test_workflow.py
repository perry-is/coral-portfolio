from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from coral_portfolio import demo
from coral_portfolio.models import MockModel, ModelUnavailable, OllamaModel
from coral_portfolio.store import LocalStore, MemoryRecord
from coral_portfolio.workflow import (
    Provider,
    assemble_context,
    effective_disclosure,
    run_workflow,
    select_provider,
)


class RecordingModel:
    """Fake model that remembers what it was sent."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, model_id: str, prompt: str) -> str:
        self.calls.append((model_id, prompt))
        return "synthetic answer"


class BrokenModel:
    def complete(self, model_id: str, prompt: str) -> str:
        raise ModelUnavailable("offline")


LOCAL_ONLY_PROVIDERS = (Provider("cloud", "cloud-model", "remote"),)


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.store = LocalStore(Path(self._dir.name) / "test.db")
        self.addCleanup(self._dir.cleanup)
        self.addCleanup(self.store.close)
        for key, content, label in demo.DEMO_MEMORIES:
            self.store.add_memory(key, content, label)

    def run_request(self, message: str, providers: tuple[Provider, ...], **overrides):
        options = dict(
            user_message=message,
            user_disclosure="cloud_allowed",
            preferred_locality="local",
            budget_chars=1200,
            providers=providers,
        )
        options.update(overrides)
        return run_workflow(self.store, **options)


class RetrievalTests(StoreTestCase):
    def test_returns_only_the_relevant_memory(self) -> None:
        results = self.store.search_memories("When is the launch checklist reviewed?")
        self.assertEqual([m.content for m in results], [demo.DEMO_MEMORIES[0][1]])

    def test_words_shared_by_every_memory_do_not_count(self) -> None:
        self.assertEqual(self.store.search_memories("What is the example team doing?"), [])

    def test_unrelated_question_retrieves_nothing(self) -> None:
        self.assertEqual(self.store.search_memories("What's the weather?"), [])


class ContextTests(unittest.TestCase):
    def test_memories_are_added_whole_or_not_at_all(self) -> None:
        memories = [MemoryRecord(1, "short fact", "cloud_allowed"), MemoryRecord(2, "x" * 500, "cloud_allowed")]
        context, included = assemble_context("Question?", memories, budget_chars=80)
        self.assertLessEqual(len(context), 80)
        self.assertEqual([m.memory_id for m in included], [1])
        self.assertNotIn("x", context.replace("Question?", ""))


class PolicyTests(unittest.TestCase):
    def test_unknown_or_missing_labels_fail_closed(self) -> None:
        self.assertEqual(effective_disclosure(["cloud_allowed", "unlabeled"]), "local_only")
        self.assertEqual(effective_disclosure([]), "local_only")

    def test_local_only_never_selects_remote(self) -> None:
        provider, _ = select_provider("local_only", "remote", LOCAL_ONLY_PROVIDERS)
        self.assertIsNone(provider)


class WorkflowTests(StoreTestCase):
    def test_retrieved_private_memory_tightens_disclosure(self) -> None:
        local, cloud = RecordingModel(), RecordingModel()
        result = self.run_request(
            "Is the team lead negotiating a raise?",
            (Provider("local", "local-model", "local", local), Provider("cloud", "cloud-model", "remote", cloud)),
            preferred_locality="remote",
        )
        self.assertEqual(result.disclosure, "local_only")
        self.assertEqual(result.locality, "local")
        self.assertEqual(cloud.calls, [])
        self.assertEqual(len(local.calls), 1)

    def test_public_memory_can_use_preferred_cloud_route(self) -> None:
        cloud = RecordingModel()
        result = self.run_request(
            "Who do we order packaging from?",
            (Provider("local", "local-model", "local"), Provider("cloud", "cloud-model", "remote", cloud)),
            preferred_locality="remote",
        )
        self.assertEqual((result.disclosure, result.locality), ("cloud_allowed", "remote"))
        self.assertEqual(cloud.calls[0][0], "cloud-model")

    def test_denied_request_never_calls_a_model_and_still_leaves_a_receipt(self) -> None:
        cloud = RecordingModel()
        result = self.run_request(
            "Is the team lead negotiating a raise?",
            (Provider("cloud", "cloud-model", "remote", cloud),),
        )
        self.assertEqual(result.decision, "denied")
        self.assertIsNone(result.answer)
        self.assertEqual(cloud.calls, [])
        receipt = self.store.receipts()[-1]
        self.assertEqual(receipt["decision"], "denied")
        self.assertIsNone(receipt["provider_id"])

    def test_model_failure_is_recorded_not_raised(self) -> None:
        result = self.run_request(
            "When is the launch checklist reviewed?", (Provider("local", "m", "local", BrokenModel()),)
        )
        self.assertEqual(result.decision, "failed")
        self.assertEqual(self.store.receipts()[-1]["decision"], "failed")

    def test_receipt_records_model_but_no_private_text(self) -> None:
        result = self.run_request(
            "Is the team lead negotiating a raise?", (Provider("local", "qwen-test", "local", MockModel()),)
        )
        receipt = json.dumps(self.store.receipts()[-1])
        self.assertIn("qwen-test", receipt)
        self.assertIn(result.context_sha256, receipt)
        for private_text in ("raise", "negotiating", "kept private", result.answer):
            self.assertNotIn(private_text, receipt)


class OllamaTests(unittest.TestCase):
    def test_sends_model_and_prompt_to_local_endpoint(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"response": " Thursday. "}'
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            answer = OllamaModel("http://localhost:11434").complete("qwen2.5:3b", "hello")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/generate")
        self.assertEqual(json.loads(request.data), {"model": "qwen2.5:3b", "prompt": "hello", "stream": False})
        self.assertEqual(answer, "Thursday.")

    def test_unreachable_server_raises_model_unavailable(self) -> None:
        with self.assertRaises(ModelUnavailable):
            OllamaModel("http://127.0.0.1:9", timeout=1).complete("m", "hello")


class DemoTests(unittest.TestCase):
    def test_demo_runs_offline_and_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            demo, "DATABASE_PATH", Path(directory) / "demo.db"
        ):
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output):
                    demo.main([])
                self.assertIn("Decision:    ALLOWED", output.getvalue())
                self.assertIn('"id": 1,', output.getvalue())  # fresh database each run


if __name__ == "__main__":
    unittest.main()
