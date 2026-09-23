"""Which person a browser counts as, for the memory.

A memory that carries things between conversations carries them between one
person's. That needs a name for the person, and the Playground has two kinds
of visitor: an AI Hub account, which is a real identity, and an anonymous
trial, which is given an identifier of its own per browser.

The anonymous one is weaker on purpose — another browser starts over — and
what it must never do is hand one visitor's memory to the next. See ADR-0020
and #45.
"""

from __future__ import annotations

import pytest

from playground.app import create_app
from playground.routes.viewer_identity import VISITOR_KEY, viewer_id


@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


def _id_in(app, **session_values):
    with app.test_request_context():
        from flask import session

        session.update(session_values)
        return viewer_id()


def test_signing_in_makes_the_account_the_person(app):
    assert _id_in(app, ai_hub_username="張先生") == "aihub:張先生"


def test_the_account_is_the_person_even_if_this_browser_had_an_identifier(app):
    assert _id_in(app, ai_hub_username="張先生", **{VISITOR_KEY: "visitor:abc"}) == "aihub:張先生"


def test_an_anonymous_browser_is_given_an_identifier_of_its_own(app):
    with app.test_request_context():
        from flask import session

        first = viewer_id()
        assert first.startswith("visitor:")
        assert session[VISITOR_KEY] == first, "it is kept, or the next call mints another"


def test_asking_twice_in_one_browser_gives_the_same_answer(app):
    with app.test_request_context():
        assert viewer_id() == viewer_id(), (
            "a new identifier every call would lose the memory between one turn and the next"
        )


def test_two_browsers_are_two_people(app):
    with app.test_request_context():
        one = viewer_id()
    with app.test_request_context():
        other = viewer_id()

    assert one != other, (
        "one visitor's memory must not be waiting for the next visitor on another machine"
    )


def test_a_blank_username_is_not_a_person(app):
    """An empty string in the session is not somebody called "" ."""
    assert _id_in(app, ai_hub_username="   ").startswith("visitor:")


def test_a_login_that_expired_does_not_fall_back_to_a_stranger(app):
    """The identifier a shared browser last held may belong to somebody else."""
    from playground.services.aihub_session import _downgrade_expired_authentication

    with app.test_request_context():
        from flask import session

        stranger = viewer_id()          # whoever used this machine before
        session["ai_hub_credential_ticket"] = "ticket"
        session["ai_hub_username"] = "張先生"
        assert viewer_id() == "aihub:張先生"

        _downgrade_expired_authentication()

        assert viewer_id() != stranger, (
            "an expired login inheriting the browser's last visitor identifier would hand "
            "that person's memory to whoever is sitting there now"
        )
        assert viewer_id().startswith("visitor:")
