"""Run the synthetic local-first workflow without calling a model."""

from __future__ import annotations

import os
from pathlib import Path

from .store import LocalStore
from .workflow import Provider, run_workflow


DEMO_MEMORY = "The example team reviews its launch checklist every Thursday."
DEMO_REQUEST = "When does the example team review its launch checklist?"
PROVIDERS = (
    Provider("local-demo", "local-placeholder", "local"),
    Provider("cloud-demo", "cloud-placeholder", "remote"),
)


def main() -> None:
    preferred = os.getenv("CORAL_PREFERRED_PROVIDER", "cloud").strip().casefold()
    if preferred not in {"local", "cloud"}:
        preferred = "local"
    preferred_locality = "remote" if preferred == "cloud" else "local"
    try:
        budget = max(1, int(os.getenv("CORAL_CONTEXT_BUDGET_CHARS", "1200")))
    except ValueError:
        budget = 1200
    disclosure = os.getenv("CORAL_DEMO_DISCLOSURE", "cloud_allowed")
    database_path = Path(".coral-local") / "coral-demo.db"

    with LocalStore(database_path) as store:
        memory_id = store.add_memory("synthetic-launch-checklist", DEMO_MEMORY, "cloud_allowed")
        result = run_workflow(
            store,
            user_message=DEMO_REQUEST,
            memory_id=memory_id,
            user_disclosure=disclosure,
            preferred_locality=preferred_locality,
            budget_chars=budget,
            providers=PROVIDERS,
        )
        print("Coral workflow demo (routing decision only; no model called)")
        print(f"Disclosure: {result.disclosure}")
        print(f"Selected route: {result.locality} ({result.provider_id})")
        print(f"Decision: {result.decision} — {result.reason}")
        print(f"Context size: {result.context_chars} characters")
        print(f"Context SHA-256: {result.context_sha256}")
        print(f"SQLite receipt ID: {result.receipt_id}")


if __name__ == "__main__":
    main()
