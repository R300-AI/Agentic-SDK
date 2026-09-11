"""The agent spec for the current Playground session.

Routes reach for the spec, not for the compiled Python text. This module is the
one place that answers "what is the session editing right now", so the Builder
and the Runner cannot disagree about it.
"""

from __future__ import annotations

from typing import Any

from flask import session

from playground.services.workflow_spec import default_spec, saved_before_0_3_0, validate_spec


def current_spec() -> dict[str, Any]:
    """Return the session's v2 spec, creating one when the session has none.

    A session that has never been through the Builder gets the default spec, and
    it is stored so every later read in the same session agrees. Nothing is
    recovered from compiled text: AI Hub holds a spec for every agent.
    """
    stored = _stored_spec()
    if stored is not None:
        return stored

    spec = default_spec()
    session["workflow_spec"] = spec
    return spec


def _stored_spec() -> dict[str, Any] | None:
    """The session's draft, or None. One definition of "this session has one"."""
    stored = session.get("workflow_spec")
    if not (isinstance(stored, dict) and stored.get("version") == "2"):
        return None
    if saved_before_0_3_0(stored):
        # A draft held since before 0.3.0 reads back in the new format, the same
        # way an agent loaded from AI Hub does — see ADR-0005.
        stored = validate_spec(stored)
        session["workflow_spec"] = stored
    return stored


def has_spec() -> bool:
    """Report whether this session is already editing an agent.

    Distinct from :func:`current_spec`, which answers "give me a spec" and
    creates one when the session has none. Use this wherever the absence of a
    draft is itself the answer, such as a route that redirects to the Builder.
    """
    return _stored_spec() is not None


def store_spec(spec: dict[str, Any]) -> None:
    """Replace the session's draft with this spec."""
    session["workflow_spec"] = spec


def clear_spec() -> None:
    """Drop the session's draft, leaving it with none."""
    session.pop("workflow_spec", None)


def reset_spec() -> dict[str, Any]:
    """Start a fresh draft, replacing whatever the session held.

    Callers that used to seed the session with default compiled text seed the
    spec instead, so the spec stays the session's one source of truth.
    """
    spec = default_spec()
    session["workflow_spec"] = spec
    return spec
