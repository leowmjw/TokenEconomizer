"""Deterministic, harness-neutral learning functions for the compiled workload.

The adapter boundary is intentionally separate: this module only consumes the
normalized event contract and never opens a harness database or transcript.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


MODEL_WEIGHTS = {
    "claude-haiku-4-5": {"cache_read": 0.10, "cache_write": 1.25, "output": 5.0},
    "claude-opus-4-6": {"cache_read": 0.10, "cache_write": 1.25, "output": 5.0},
    "claude-sonnet-4-6": {"cache_read": 0.10, "cache_write": 1.25, "output": 5.0},
    "gpt-5.3-codex": {"cache_read": 0.0971, "cache_write": 0.0, "output": 8.0},
    "gpt-5.6-sol": {"cache_read": 0.10, "cache_write": 1.25, "output": 6.0},
    "gpt-5.6-luna": {"cache_read": 0.10, "cache_write": 1.25, "output": 6.0},
    "gpt-5-codex": {"cache_read": 0.10, "cache_write": 1.0, "output": 8.0},
}
PROTECTED_TOOLS = {"shell", "read", "search", "edit", "write"}
EVENT_KINDS = {"session_start", "prompt", "tool_call", "tool_result", "session_end"}
REQUIRED_EVENT_FIELDS = {"harness", "session_id", "sequence", "kind"}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _tool_family(name: Any) -> str:
    text = str(name or "").strip().lower()
    for family in PROTECTED_TOOLS:
        if family in text:
            return family
    return text


def _state_namespace(manifest: Mapping[str, Any]) -> str:
    material = "\0".join(str(manifest[key]) for key in ("repository", "harness", "stream_id"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def validate_log_manifest(manifest: Mapping[str, Any]) -> dict:
    """Validate the portable manifest without resolving a harness adapter."""
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be an object")
    required = ("repository", "stream_id", "harness", "log_sources", "state_dir", "model")
    missing = [key for key in required if not str(manifest.get(key, "")).strip()]
    if missing:
        raise ValueError("manifest missing required fields: " + ", ".join(missing))
    if not isinstance(manifest["log_sources"], list) or not manifest["log_sources"]:
        raise ValueError("manifest.log_sources must be a non-empty list")
    seen = set()
    sources = []
    for source in manifest["log_sources"]:
        if not isinstance(source, Mapping) or not str(source.get("path", "")).strip():
            raise ValueError("each log source needs a path")
        path = str(source["path"])
        if path in seen:
            raise ValueError("duplicate log source: " + path)
        seen.add(path)
        if ".." in path.replace("\\", "/").split("/"):
            raise ValueError("path traversal is not allowed in log sources")
        sources.append({"path": path, "format": source.get("format", "unknown")})
    state_dir = str(manifest["state_dir"])
    if ".." in state_dir.replace("\\", "/").split("/"):
        raise ValueError("path traversal is not allowed in state_dir")
    operation = str(manifest.get("operation", "list"))
    if operation not in {"list", "remembered", "review", "train"}:
        raise ValueError("operation must be list, remembered, review, or train")
    ids = manifest.get("selected_conversation_ids", [])
    if ids is None:
        ids = []
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("selected_conversation_ids must be a list of non-empty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("selected_conversation_ids must not contain duplicates")
    model = str(manifest["model"])
    if model not in MODEL_WEIGHTS:
        raise ValueError("unknown billed model: " + model)
    return {
        "repository": str(manifest["repository"]),
        "stream_id": str(manifest["stream_id"]),
        "harness": str(manifest["harness"]),
        "log_sources": sources,
        "state_dir": state_dir,
        "model": model,
        "seed": manifest.get("seed", 0),
        "policy_state": deepcopy(manifest.get("policy_state") or {}),
        "operation": operation,
        "selected_conversation_ids": list(ids),
        "state_namespace": _state_namespace(manifest),
    }


def determine_training_selection(manifest: Mapping[str, Any], discovery: Mapping[str, Any]) -> dict:
    """Decide whether train needs explicit human selection; never train by default."""
    validated = validate_log_manifest(manifest)
    explicit = list(validated["selected_conversation_ids"])
    operation = validated["operation"]
    needs = operation == "train" and not explicit
    return {
        "operation": operation,
        "needs_user_selection": needs,
        "explicit_ids": explicit,
        "discovered_count": len(_as_list(discovery.get("conversations"))),
        "consent_required": needs,
    }


def resolve_training_selection(
    explicit_ids: Optional[list], selection: Optional[Mapping[str, Any]]
) -> dict:
    """Resolve explicit IDs or a gate payload, preserving the consent source."""
    ids = list(explicit_ids or [])
    source = "explicit" if ids else "none"
    if not ids and isinstance(selection, Mapping):
        gate_ids = selection.get("conversation_ids", [])
        if not isinstance(gate_ids, list) or any(not isinstance(item, str) or not item for item in gate_ids):
            raise ValueError("training_selection.conversation_ids must be non-empty strings")
        ids = list(dict.fromkeys(gate_ids))
        source = "human_selection" if ids else "none"
    return {
        "conversation_ids": ids,
        "selection_source": source,
        "selected_count": len(ids),
        "training_authorized": bool(ids),
    }


def normalize_harness_events(log_payload: Mapping[str, Any]) -> list:
    """Validate the adapter result and return a copied, ordered event list."""
    if not isinstance(log_payload, Mapping):
        raise ValueError("adapter output must be an object")
    events = log_payload.get("events")
    if not isinstance(events, list):
        raise ValueError("adapter output must contain an events list")
    last_by_session: Dict[str, Any] = {}
    result = []
    for index, original in enumerate(events):
        if not isinstance(original, Mapping):
            raise ValueError("event %d must be an object" % index)
        missing = REQUIRED_EVENT_FIELDS - set(original)
        if missing:
            raise ValueError("event %d missing: %s" % (index, ", ".join(sorted(missing))))
        event = dict(original)
        if event["kind"] not in EVENT_KINDS:
            raise ValueError("event %d has unknown kind %r" % (index, event["kind"]))
        if not isinstance(event["session_id"], str) or not event["session_id"]:
            raise ValueError("event %d has invalid session_id" % index)
        sequence = event["sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ValueError("event %d sequence must be an integer" % index)
        prior = last_by_session.get(event["session_id"])
        if prior is not None and sequence <= prior:
            raise ValueError("event sequence must increase within each session")
        last_by_session[event["session_id"]] = sequence
        event.setdefault("timestamp", None)
        event.setdefault("tool", None)
        event.setdefault("ok", None)
        event.setdefault("args", {})
        event.setdefault("error_signature", None)
        event.setdefault("edited_files", [])
        event.setdefault("test_run", False)
        event.setdefault("tools_loaded", [])
        event.setdefault("tools_used", [])
        event.setdefault("usage", None)
        event.setdefault("resolved", None)
        event.setdefault("fact_candidates", [])
        event.setdefault("judge", None)
        event.setdefault("raw", {})
        if not isinstance(event["edited_files"], list) or not isinstance(event["tools_loaded"], list):
            raise ValueError("event %d list fields are malformed" % index)
        if event["usage"] is not None and not isinstance(event["usage"], Mapping):
            raise ValueError("event %d usage must be an object or null" % index)
        event["raw"] = dict(event["raw"]) if isinstance(event["raw"], Mapping) else {}
        result.append(event)
    return result


def _session_ids(events: Iterable[Mapping[str, Any]]) -> list:
    seen = []
    for event in events:
        sid = event["session_id"]
        if sid not in seen:
            seen.append(sid)
    return seen


def _fold_facts(events: list, prior: Mapping[str, Any], prior_sessions: int) -> dict:
    facts = deepcopy(prior.get("facts") or {}) if isinstance(prior, Mapping) else {}
    for event in events:
        for candidate in _as_list(event.get("fact_candidates")):
            if not isinstance(candidate, Mapping):
                continue
            fact_id = str(candidate.get("id", "")).strip()
            claim = str(candidate.get("claim", "")).strip()
            if not fact_id or not claim:
                continue
            fact = facts.setdefault(fact_id, {
                "id": fact_id,
                "claim": claim,
                "context_key": candidate.get("context_key"),
                "confirmations": 0,
                "contexts": [],
                "exercised": 0,
                "fired": 0,
                "contradictions": 0,
                "high_stakes": bool(candidate.get("high_stakes", False)),
                "status": "candidate",
                "injectable": False,
            })
            fact["claim"] = claim
            fact["high_stakes"] = fact["high_stakes"] or bool(candidate.get("high_stakes", False))
            verdict = candidate.get("verdict")
            context = candidate.get("context_key")
            if verdict == "confirm":
                fact["confirmations"] += 1
                if context and context not in fact["contexts"]:
                    fact["contexts"].append(context)
            elif verdict in {"contradict", "contradiction", "reject"}:
                fact["contradictions"] += 1
            if candidate.get("exercised"):
                fact["exercised"] += 1
            if candidate.get("fired"):
                fact["fired"] += 1
    for fact in facts.values():
        enough_context = len(fact["contexts"]) >= 2 if fact["contexts"] else True
        promoted = fact["confirmations"] >= 3 and enough_context
        retired = fact["contradictions"] > 0 and (fact["high_stakes"] or fact["confirmations"] - fact["contradictions"] < 0)
        fact["status"] = "retired" if retired else ("active" if promoted else "candidate")
        rate = fact["fired"] / fact["exercised"] if fact["exercised"] else 0.0
        fact["injectable"] = bool(prior_sessions > 0 and fact["status"] == "active"
                                    and fact["exercised"] >= 4 and rate >= 0.40)
        fact["firing_rate"] = round(rate, 4)
    return facts


def _fold_tools(events: list, prior: Mapping[str, Any]) -> dict:
    state = deepcopy(prior.get("tools") or {}) if isinstance(prior, Mapping) else {}
    records = state.setdefault("evidence", {})
    for session_id in _session_ids(events):
        session_events = [event for event in events if event["session_id"] == session_id]
        loaded = set(tool for event in session_events for tool in _as_list(event.get("tools_loaded")))
        used = set(tool for event in session_events for tool in _as_list(event.get("tools_used")))
        used.update(event.get("tool") for event in session_events if event.get("kind") == "tool_call" and event.get("tool"))
        prompts = sum(event.get("kind") == "prompt" for event in session_events)
        for tool in loaded:
            rec = records.setdefault(tool, {"loaded_sessions": 0, "unused_sessions": 0, "prompts": 0, "ever_used": False})
            rec["loaded_sessions"] += 1
            rec["prompts"] += prompts
            if tool in used:
                rec["ever_used"] = True
                rec["unused_sessions"] = 0
            else:
                rec["unused_sessions"] += 1
        for tool in used:
            rec = records.setdefault(tool, {"loaded_sessions": 0, "unused_sessions": 0, "prompts": 0, "ever_used": False})
            rec["ever_used"] = True
            rec["unused_sessions"] = 0
    exclusions = []
    for tool, rec in records.items():
        family = _tool_family(tool)
        threshold = (rec["prompts"] >= 10 and rec["loaded_sessions"] >= 2) or rec["loaded_sessions"] >= 5
        if threshold and not rec["ever_used"] and family not in PROTECTED_TOOLS:
            exclusions.append(tool)
    state["exclusions"] = sorted(exclusions)
    return state


def _loop_observation(events: list) -> dict:
    by_session = {}
    recommendations = []
    for sid in _session_ids(events):
        session = [event for event in events if event["session_id"] == sid]
        calls = sum(event.get("kind") == "tool_call" for event in session)
        errors = [event.get("error_signature") for event in session if event.get("error_signature")]
        counts = Counter(errors)
        repeated = sum(count - 1 for count in counts.values() if count > 1)
        files = Counter(file for event in session for file in _as_list(event.get("edited_files")))
        distinct = len(files)
        churn = max(files.values(), default=0)
        gate = calls >= 18 and (repeated >= 1 or len(errors) >= 8)
        strict = (calls >= 20 and (churn >= 4 or distinct >= 3) and len(errors) >= 6
                  and (repeated / len(errors) if errors else 0.0) >= 0.20)
        accepted_judge = any(
            isinstance(event.get("judge"), Mapping)
            and event["judge"].get("stuck") is True
            and float(event["judge"].get("confidence", 0.0)) >= 0.70
            for event in session
        )
        would_redirect = bool(gate and (accepted_judge or strict))
        by_session[sid] = {
            "tool_calls": calls,
            "error_outputs": len(errors),
            "repeated_failures": repeated,
            "distinct_edited_files": distinct,
            "max_edits_one_file": churn,
            "gate_open": gate,
            "strict_fallback": strict,
            "would_redirect": would_redirect,
        }
        if would_redirect:
            recommendations.append({"session_id": sid, "would_redirect": True, "reason": "sustained repeated failure"})
    return {"sessions": by_session, "recommendations": recommendations}


def fold_repository_learning(events: list, policy_state: Optional[Mapping[str, Any]]) -> dict:
    """Fold one completed normalized trace into reversible repository policy state."""
    prior = policy_state if isinstance(policy_state, Mapping) else {}
    prior_session_count = int(prior.get("session_count", 0) or 0)
    facts = _fold_facts(events, prior, prior_session_count)
    tools = _fold_tools(events, prior)
    loops = _loop_observation(events)
    state = {
        "session_count": prior_session_count + len(_session_ids(events)),
        "facts": facts,
        "tools": tools,
        "loop_guard": loops,
    }
    return {
        "next_policy_state": state,
        "active_facts": sorted(fact_id for fact_id, fact in facts.items() if fact["status"] == "active"),
        "injectable_facts": sorted(fact_id for fact_id, fact in facts.items() if fact["injectable"]),
        "retired_facts": sorted(fact_id for fact_id, fact in facts.items() if fact["status"] == "retired"),
        "tool_exclusions": sorted(tools.get("exclusions", [])),
        "loop_guard": loops,
        "would_redirect": len(loops["recommendations"]),
        "sessions_learned": _session_ids(events),
    }


def _effective_usage(usage: Mapping[str, Any], weights: Mapping[str, float]) -> Optional[float]:
    if usage.get("input_tokens") is not None:
        input_tokens = float(usage.get("input_tokens") or 0)
        cache_read = float(usage.get("cache_read_input_tokens") or 0)
        cache_write = float(usage.get("cache_creation_input_tokens") or 0)
        output = float(usage.get("output_tokens") or 0)
        return (input_tokens + cache_read * weights["cache_read"]
                + cache_write * weights["cache_write"] + output * weights["output"])
    if usage.get("tokens_total") is not None:
        return float(usage["tokens_total"])
    return None


def compute_cache_aware_cost(events: list, model: str) -> dict:
    """Price logged usage, preserving unknown usage instead of treating it as zero."""
    if model not in MODEL_WEIGHTS:
        raise ValueError("unknown billed model: " + str(model))
    weights = MODEL_WEIGHTS[model]
    total = 0.0
    execution = 0.0
    overhead = 0.0
    unknown = 0
    fallback = 0
    for event in events:
        usage = event.get("usage")
        if usage is None:
            continue
        if not isinstance(usage, Mapping):
            unknown += 1
            continue
        value = _effective_usage(usage, weights)
        if value is None:
            unknown += 1
            continue
        if usage.get("input_tokens") is None:
            fallback += 1
        total += value
        role = usage.get("role", "execution")
        if role in {"proposer", "judge", "redirect"}:
            overhead += value
        else:
            execution += value
    usage_events = sum(event.get("usage") is not None for event in events)
    status = "unknown" if unknown or not usage_events else ("legacy_fallback" if fallback else "ok")
    return {
        "model": model,
        "effective_execution_tokens": round(execution, 4) if status != "unknown" or execution else None,
        "mechanism_overhead_tokens": round(overhead, 4) if status != "unknown" or overhead else None,
        "effective_total_tokens": round(total, 4) if status != "unknown" else None,
        "usage_events": usage_events,
        "unknown_usage_events": unknown,
        "cost_status": status,
    }


def render_review_summary(
    manifest: Mapping[str, Any],
    discovery: Mapping[str, Any],
    selection: Mapping[str, Any],
    events: list,
    learning: Mapping[str, Any],
    cost: Mapping[str, Any],
) -> dict:
    """Render the auditable result; this is also the review surface for the CLI."""
    sessions = _session_ids(events)
    resolved = sum(event.get("resolved") is True for event in events)
    unknown_outcomes = sum(event.get("resolved") is None for event in events if event.get("kind") == "session_end")
    discovered = [item.get("conversation_id") for item in _as_list(discovery.get("conversations"))]
    selected = list(selection.get("conversation_ids", []))
    learned = list(learning.get("sessions_learned", []))
    return {
        "repository": manifest["repository"],
        "stream_id": manifest["stream_id"],
        "harness": manifest["harness"],
        "model": manifest["model"],
        "operation": manifest.get("operation", "list"),
        "source_digest": hashlib.sha256(json.dumps(events, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "discovered_conversations": discovered,
        "selected_conversations": selected,
        "read_conversations": sessions,
        "learned_conversations": learned,
        "sessions": len(sessions),
        "resolved": resolved,
        "unknown_outcomes": unknown_outcomes,
        "effective_execution_tokens": cost.get("effective_execution_tokens"),
        "mechanism_overhead_tokens": cost.get("mechanism_overhead_tokens"),
        "cost_status": cost.get("cost_status"),
        "remembered": {
            "active_facts": learning.get("active_facts", []),
            "injectable_facts": learning.get("injectable_facts", []),
            "retired_facts": learning.get("retired_facts", []),
            "tool_exclusions": learning.get("tool_exclusions", []),
            "loop_guard": learning.get("loop_guard", {}),
        },
        "would_redirect": learning.get("would_redirect", 0),
        "contract_failures": [],
        "next_state_namespace": manifest.get("state_namespace", _state_namespace(manifest)),
        "state_write": "caller_must_atomically_persist_next_policy_state",
    }
