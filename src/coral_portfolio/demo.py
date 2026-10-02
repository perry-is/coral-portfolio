"""Run Coral against a few synthetic memories.

    coral-demo                                    # mock model, no setup needed
    coral-demo --ask "Who is the team lead negotiating with?"   # sensitive memory -> local only
    coral-demo --ask "..." --no-local             # local model offline -> denied, receipt still written
    coral-demo --ollama --model qwen2.5:3b        # real answer from your local Ollama
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import MockModel, ModelClient, OllamaModel
from .store import LocalStore
from .workflow import Provider, run_workflow

# All fictional. Note the mix of labels: one memory is private and one was never labeled.
DEMO_MEMORIES = (
    ("launch-checklist", "The example team reviews its launch checklist every Thursday at 10am.", "cloud_allowed"),
    ("packaging-vendor", "The example team orders packaging from Northwind Supply.", "cloud_allowed"),
    ("lead-raise", "The example team lead is negotiating a raise and wants that kept private.", "local_only"),
    ("quarterly-review", "The example team's quarterly review moved to the last Friday of the month.", "unlabeled"),
)
DEFAULT_QUESTION = "When does the example team review its launch checklist?"
DATABASE_PATH = Path(".coral-local") / "coral-demo.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ask", default=DEFAULT_QUESTION, help="question to answer from memory")
    parser.add_argument("--disclosure", default="cloud_allowed", help="label for the request itself")
    parser.add_argument("--prefer", choices=("local", "cloud"), default="local", help="preferred route when policy allows")
    parser.add_argument("--budget", type=int, default=1200, help="context budget in characters")
    parser.add_argument("--no-local", action="store_true", help="simulate the local model being offline")
    parser.add_argument("--ollama", action="store_true", help="answer with a real local Ollama model")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default="qwen2.5:3b", help="local model name")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    local_client: ModelClient = OllamaModel(args.ollama_url) if args.ollama else MockModel()
    providers = [Provider("cloud-example", "cloud-model-placeholder", "remote")]  # no client: routing only
    if not args.no_local:
        model_id = args.model if args.ollama else "mock"
        providers.insert(0, Provider("local-ollama" if args.ollama else "local-mock", model_id, "local", local_client))

    DATABASE_PATH.unlink(missing_ok=True)  # start each demo run from the same fictional state
    with LocalStore(DATABASE_PATH) as store:
        for key, content, label in DEMO_MEMORIES:
            store.add_memory(key, content, label)
        result = run_workflow(
            store,
            user_message=args.ask,
            user_disclosure=args.disclosure,
            preferred_locality="remote" if args.prefer == "cloud" else "local",
            budget_chars=max(1, args.budget),
            providers=tuple(providers),
        )
        receipt = store.receipts()[-1]

    print(f"Request:     {args.ask}")
    print(f"Memories:    {', '.join(result.source_refs) or 'none matched'}")
    print(f"Disclosure:  {result.disclosure}")
    route = f"{result.locality} ({result.provider_id}, model {result.model_id})" if result.provider_id else "none"
    print(f"Route:       {route}")
    print(f"Decision:    {result.decision.upper()} - {result.reason}")
    if result.answer:
        print(f"Answer:      {result.answer}")
    print("\nReceipt (what was stored - no request, memory, or answer text):")
    print(json.dumps({k: receipt[k] for k in receipt if k != "created_at"}, indent=2))


if __name__ == "__main__":
    main()
