"""Retrieve -> bound context -> check disclosure -> route -> answer -> receipt."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

from .models import ModelClient, ModelUnavailable
from .store import LocalStore, MemoryRecord


POLICY_VERSION = "disclosure-v2"
DISCLOSURE_LEVELS = ("cloud_allowed", "local_only")

PROMPT_HEADER = (
    "Answer the user's request using only the memories provided. "
    "If they don't contain the answer, say so plainly.\n\n"
)


@dataclass(frozen=True)
class Provider:
    provider_id: str
    model_id: str
    locality: str  # "local" or "remote"
    client: ModelClient | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class WorkflowResult:
    decision: str  # "allowed", "denied", or "failed"
    reason: str
    disclosure: str
    provider_id: str | None
    locality: str | None
    model_id: str | None
    source_refs: tuple[str, ...]
    context_chars: int
    context_sha256: str
    receipt_id: int
    answer: str | None


def assemble_context(
    user_message: str, memories: list[MemoryRecord], budget_chars: int
) -> tuple[str, list[MemoryRecord]]:
    """Build a bounded context and report which memories actually made it in.

    The request is always kept. Memories are added whole, in relevance order,
    until the budget is reached; a memory is never cut in half, because half a
    fact can be worse than no fact.
    """
    if budget_chars < 1:
        raise ValueError("budget_chars must be positive")
    lines = [f"User request: {user_message}"[:budget_chars]]
    included: list[MemoryRecord] = []
    for memory in memories:
        candidate = "\n".join([*lines, f"Relevant memory: {memory.content}"])
        if len(candidate) <= budget_chars:
            lines.append(f"Relevant memory: {memory.content}")
            included.append(memory)
    return "\n".join(lines), included


def effective_disclosure(classifications: list[str]) -> str:
    """Use the strictest label present. Missing or unknown labels mean local-only."""
    if not classifications:
        return "local_only"
    normalized = {value.strip().casefold().replace("-", "_") for value in classifications}
    if not normalized <= set(DISCLOSURE_LEVELS):
        return "local_only"
    return "local_only" if "local_only" in normalized else "cloud_allowed"


def select_provider(
    disclosure: str, preferred: str, providers: tuple[Provider, ...]
) -> tuple[Provider | None, str]:
    """Pick from providers the policy allows. Returns (None, reason) if none are."""
    eligible = [p for p in providers if disclosure == "cloud_allowed" or p.locality == "local"]
    if not eligible:
        return None, f"no provider is eligible for {disclosure} content"
    preferred_match = next((p for p in eligible if p.locality == preferred), None)
    if preferred_match is not None:
        return preferred_match, "preferred eligible provider"
    local = next((p for p in eligible if p.locality == "local"), None)
    if local is not None:
        return local, "local fallback"
    return eligible[0], "first eligible provider"


def run_workflow(
    store: LocalStore,
    *,
    user_message: str,
    user_disclosure: str,
    preferred_locality: str,
    budget_chars: int,
    providers: tuple[Provider, ...],
    memory_limit: int = 3,
) -> WorkflowResult:
    retrieved = store.search_memories(user_message, limit=memory_limit)
    context, included = assemble_context(user_message, retrieved, budget_chars)
    # Disclosure is judged on what would actually be sent, not on the request alone.
    disclosure = effective_disclosure([user_disclosure, *(m.disclosure for m in included)])
    source_refs = tuple(f"memory:{m.memory_id}" for m in included)
    context_digest = _sha256(context)

    provider, reason = select_provider(disclosure, preferred_locality, providers)
    answer: str | None = None
    if provider is None:
        decision = "denied"  # fail closed: the model is never called
    elif provider.client is None:
        decision, reason = "allowed", f"{reason}; routing only (no client configured)"
    else:
        try:
            answer = provider.client.complete(provider.model_id, PROMPT_HEADER + context)
            decision = "allowed"
        except ModelUnavailable as exc:
            decision, reason = "failed", f"{reason}; {exc}"

    receipt_id = store.write_receipt(
        {
            "operation_id": str(uuid.uuid4()),
            "purpose": "answer_request",
            "provider_id": provider.provider_id if provider else None,
            "provider_locality": provider.locality if provider else None,
            "model_id": provider.model_id if provider else None,
            "disclosure": disclosure,
            "decision": decision,
            "reason": reason,
            "source_refs_json": json.dumps(list(source_refs), separators=(",", ":")),
            "context_sha256": context_digest,
            "response_sha256": _sha256(answer) if answer is not None else None,
            "policy_version": POLICY_VERSION,
        }
    )
    return WorkflowResult(
        decision=decision,
        reason=reason,
        disclosure=disclosure,
        provider_id=provider.provider_id if provider else None,
        locality=provider.locality if provider else None,
        model_id=provider.model_id if provider else None,
        source_refs=source_refs,
        context_chars=len(context),
        context_sha256=context_digest,
        receipt_id=receipt_id,
        answer=answer,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
