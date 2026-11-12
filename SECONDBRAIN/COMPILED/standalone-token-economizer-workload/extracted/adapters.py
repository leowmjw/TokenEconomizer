"""Harness adapter boundary.

No Zed, Claude Code, or CommandCode format is assumed until a real fixture is
provided. These contract stubs make the missing integration explicit.
"""


def discover_recent_conversations(manifest):
    """Return at most ten completed metadata records per configured adapter.

    The generic compiler has no vendor fixture or adapter registry to consult.
    A concrete adapter must discover records using explicit manifest sources,
    preserve adapter ordering, and report unknown ordering instead of using
    filesystem mtime.
    """
    raise NotImplementedError(
        "conversation discovery requires a real harness adapter fixture for "
        "the manifest's harness; do not guess Zed/Claude Code/CommandCode paths"
    )


def read_selected_harness_logs(manifest, selection):
    """Read only explicitly selected conversation IDs through the adapter.

    A concrete adapter must return {"events": [...]} in the normalized input
    contract's pre-normalization shape and must not mutate source logs.
    """
    raise NotImplementedError(
        "selected-log reading requires a real harness adapter fixture and a "
        "registered parser for the manifest's harness"
    )
