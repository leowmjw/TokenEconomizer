import unittest

from extracted.core import (
    compute_cache_aware_cost,
    determine_training_selection,
    fold_repository_learning,
    normalize_harness_events,
    render_review_summary,
    resolve_training_selection,
    validate_log_manifest,
)


BASE_MANIFEST = {
    "repository": "repo-a",
    "stream_id": "daily",
    "harness": "zed",
    "log_sources": [{"path": "/logs/a.jsonl", "format": "jsonl"}],
    "state_dir": "/state/repo-a",
    "model": "claude-sonnet-4-6",
    "operation": "train",
}


def normalized(events):
    return normalize_harness_events({"events": events})


def event(session, sequence, kind="tool_result", **extra):
    value = {
        "harness": "zed",
        "session_id": session,
        "sequence": sequence,
        "kind": kind,
        "timestamp": None,
        "tool": None,
        "ok": True,
        "args": {},
        "error_signature": None,
        "edited_files": [],
        "test_run": False,
        "tools_loaded": [],
        "tools_used": [],
        "usage": None,
        "resolved": None,
        "fact_candidates": [],
        "raw": {},
    }
    value.update(extra)
    return value


class CoreContractTests(unittest.TestCase):
    def test_manifest_and_selection_require_consent(self):
        validated = validate_log_manifest(BASE_MANIFEST)
        decision = determine_training_selection(validated, {"conversations": [{"conversation_id": "s1"}]})
        self.assertTrue(decision["needs_user_selection"])
        self.assertEqual(resolve_training_selection([], {"conversation_ids": ["s1"]})["selection_source"], "human_selection")
        self.assertEqual(resolve_training_selection(["s2"], {"conversation_ids": ["s1"]})["conversation_ids"], ["s2"])

    def test_first_session_has_no_injected_fact_but_second_can(self):
        candidates = [
            {
                "id": "canonical-check",
                "claim": "Use mise run check.",
                "context_key": "src-a" if i % 2 == 0 else "src-b",
                "exercised": True,
                "fired": i < 2,
                "verdict": "confirm",
            }
            for i in range(4)
        ]
        first = normalized([
            event("s1", i + 1, kind="tool_result", fact_candidates=[c])
            for i, c in enumerate(candidates)
        ])
        learned_first = fold_repository_learning(first, {})
        self.assertEqual(learned_first["injectable_facts"], [])
        second = normalized([
            event("s2", 1, fact_candidates=[{
                "id": "canonical-check", "claim": "Use mise run check.",
                "context_key": "src-c", "exercised": True, "fired": True,
                "verdict": "confirm",
            }])
        ])
        learned_second = fold_repository_learning(second, learned_first["next_policy_state"])
        self.assertIn("canonical-check", learned_second["injectable_facts"])

    def test_tool_pruning_threshold_and_protected_or_used_tools(self):
        events = []
        sequence = 1
        for session in ("s1", "s2"):
            for _ in range(5):
                events.append(event(session, sequence, kind="prompt", tools_loaded=["unused", "shell", "Read"], tools_used=[]))
                sequence += 1
        events.append(event("s2", sequence, kind="tool_call", tool="Read", tools_used=["Read"]))
        learned = fold_repository_learning(normalized(events), {})
        self.assertIn("unused", learned["tool_exclusions"])
        self.assertNotIn("shell", learned["tool_exclusions"])
        self.assertNotIn("Read", learned["tool_exclusions"])

    def test_repeated_failures_recommend_redirect_but_changing_failures_do_not(self):
        repeated = [
            event("stuck", i + 1, kind="tool_call", tool="Edit", error_signature="same-error",
                  edited_files=["src/a.py"])
            for i in range(20)
        ]
        changing = [
            event("productive", i + 1, kind="tool_call", tool="Edit", error_signature="error-%d" % i,
                  edited_files=["src/%d.py" % (i % 3)])
            for i in range(20)
        ]
        repeated_result = fold_repository_learning(normalized(repeated), {})
        changing_result = fold_repository_learning(normalized(changing), {})
        self.assertEqual(repeated_result["would_redirect"], 1)
        self.assertEqual(changing_result["would_redirect"], 0)

    def test_cost_preserves_unknown_usage_and_prices_breakdown(self):
        events = normalized([
            event("s1", 1, usage={"input_tokens": 100, "cache_read_input_tokens": 50,
                                  "cache_creation_input_tokens": 20, "output_tokens": 10}),
            event("s1", 2, usage={"role": "judge", "tokens_total": 5}),
            event("s1", 3, usage={}),
        ])
        result = compute_cache_aware_cost(events, "claude-sonnet-4-6")
        self.assertEqual(result["cost_status"], "unknown")
        self.assertEqual(result["unknown_usage_events"], 1)
        self.assertEqual(result["mechanism_overhead_tokens"], 5.0)
        with self.assertRaises(ValueError):
            compute_cache_aware_cost(events, "not-a-real-model")

    def test_summary_separates_discovered_selected_read_and_learned(self):
        events = normalized([event("s1", 1, kind="session_end", resolved=None)])
        manifest = validate_log_manifest(BASE_MANIFEST)
        learning = fold_repository_learning(events, {})
        cost = compute_cache_aware_cost(events, manifest["model"])
        summary = render_review_summary(
            manifest,
            {"conversations": [{"conversation_id": "s1"}, {"conversation_id": "s2"}]},
            {"conversation_ids": ["s1"]},
            events,
            learning,
            cost,
        )
        self.assertEqual(summary["discovered_conversations"], ["s1", "s2"])
        self.assertEqual(summary["selected_conversations"], ["s1"])
        self.assertEqual(summary["read_conversations"], ["s1"])
        self.assertEqual(summary["unknown_outcomes"], 1)


if __name__ == "__main__":
    unittest.main()
