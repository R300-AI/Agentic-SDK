"""Who the person at this browser is, as far as the memory is concerned.

A memory that carries things between conversations carries them between one
person's conversations. That needs a name for the person, and the Playground
has two kinds of visitor:

An AI Hub account is a real identity — the same person on another machine is
the same person, and what their agent remembered is waiting for them.

An anonymous trial has none. Rather than leave everyone anonymous sharing one
memory, each browser gets an identifier of its own, minted on first use and
kept in that browser's session. It is weaker on purpose: the same person in
another browser starts over, which is the safe direction to be wrong in. What
it never does is hand one visitor's memory to the next one.

It lives with the routes, not the services: it reads the current request's
session, and a service that does that cannot be called from anywhere else.
The services take who it is as an argument. See ADR-0020.
"""

from __future__ import annotations

import uuid

from flask import session

from playground.services.aihub_session import VISITOR_KEY


def viewer_id() -> str:
    """The identifier this browser's memory is kept under.

    Signed in, that is the AI Hub account. Anonymous, it is an identifier for
    this browser, minted here the first time anything asks.
    """
    username = str(session.get("ai_hub_username") or "").strip()
    if username:
        return f"aihub:{username}"
    visitor = session.get(VISITOR_KEY)
    if not isinstance(visitor, str) or not visitor:
        visitor = f"visitor:{uuid.uuid4().hex}"
        session[VISITOR_KEY] = visitor
    return visitor
