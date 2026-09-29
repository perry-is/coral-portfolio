"""Bounded context, fail-closed disclosure, route selection, and receipt flow."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from .store import LocalStore


POLICY_VERSION = "portfolio-disclosure-v1"


@dataclass(frozen=True)
class Provider:
    provider_id: str
    model_id: str
    locality: str


@dataclass(frozen=True)
class WorkflowResult:
    provider_id: str
    locality: str
    disclosure: str
    decision: str
    reason: str
    receipt_id: int
    context_sha256: str
    context_chars: int


def assemble_context(user_message: str, memories: list[str], budget_chars: int) -> str:
    """Build a deterministic, size-bounded context from ordered evidence."""
    if budget_chars < 1:
        raise ValueError("budget_chars must be positive")
    sections = [f"User request: {user_message}"]
    for memory in memories:
        sections.append(f"Relevant memory: {memory}")
    rendered = "\n".join(sections)
    if len(rendered) <= budget_chars:
        return rendered
    # Keep the request intact when possible; truncate only appended evidence.
    request = sections[0]
    if len(request) >= budget_chars:
        return request[:budget_chars]
    prefix = request + "\n"
    return prefix + "\n".join(sections[1:])[: budget_chars - len(prefix)]


def effective_disclosure(classifications: list[str]) -> str:
    """Use the strictest class; unknown values are local-only by default."""
    if not classifications:
        return "local_only"
    normalized = {value.strip().casefold().replace("-", "_") for value in classifications}
    if any(value not in {"cloud_allowed", "local_only"} for value in normalized):
        return "local_only"
    return "local_only" if "local_only" in normalized else "cloud_allowed"


def select_provider(
    disclosure: str,
    preferred: str,
    providers: tuple[Provider, ...],
) -> tuple[Provider, str]:
    """Select only from policy-eligible providers, with local as safe fallback."""
    eligible = tuple(
        provider for provider in providers
        if disclosure == "cloud_allowed" or provider.locality == "local"
    )
    if not eligible:
        raise RuntimeError("No provider is eligible for the disclosure class")
    match = next(
        (provider for provider in eligible if provider.locality == preferred), None
    )
    if match is not None:
        return match, "preferred eligible provider"
    local = next((provider for provider in eligible if provider.locality == "local"), None)
    if local is not None:
        return local, "local fallback"
    return eligible[0], "first eligible provider"


def run_workflow(
    store: LocalStore,
    *,
    user_message: str,
    memory_id: int,
    user_disclosure: str,
    preferred_locality: str,
    budget_chars: int,
    providers: tuple[Provider, ...],
) -> WorkflowResult:
    memory = store.get_memory(memory_id)
    context = assemble_context(user_message, [memory.content], budget_chars)
    disclosure = effective_disclosure([user_disclosure, memory.disclosure])
    provider, reason = select_provider(disclosure, preferred_locality, providers)
    digest = hashlib.sha256(context.encode("utf-8")).hexdigest()
    source_refs = json.dumps([f"memory:{memory.memory_id}"], separators=(",", ":"))
    receipt_id = store.write_receipt(
        {
            "operation_id": str(uuid.uuid4()),
            "purpose": "demo.answer_route",
            "provider_id": provider.provider_id,
            "provider_locality": provider.locality,
            "disclosure": disclosure,
            "decision": "allowed",
            "reason": reason,
            "source_refs_json": source_refs,
            "context_sha256": digest,
            "policy_version": POLICY_VERSION,
        }
    )
    return WorkflowResult(
        provider.provider_id, provider.locality, disclosure, "allowed", reason,
        receipt_id, digest, len(context),
    )
