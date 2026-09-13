from __future__ import annotations

import pytest

from playground.services.voice_session import (
    VoiceSessionRegistry,
    unknown_session_message,
)


def test_a_running_answer_can_be_stopped_from_somewhere_else():
    """The browser hears the person speak; the workflow is on another request.

    Without a way to find the run from outside it, the interjection has nothing
    to interrupt.
    """
    registry = VoiceSessionRegistry()
    token = registry.open("session-1")

    stopped = registry.interject("session-1", heard_seconds=1.5)

    assert stopped is True
    assert token.cancelled is True
    assert token.reason == "interjection"


def test_the_interjection_carries_how_long_the_person_listened():
    """Only the player knows this, and the next turn depends on it."""
    registry = VoiceSessionRegistry()
    token = registry.open("session-1")

    registry.interject("session-1", heard_seconds=2.25)

    assert token.payload["heard_seconds"] == 2.25


def test_interrupting_a_session_that_is_not_running_says_so():
    registry = VoiceSessionRegistry()

    assert registry.interject("never-opened", heard_seconds=1.0) is False
    assert "已經結束" in unknown_session_message()


def test_closing_a_session_forgets_it():
    """A registry that only grows is a leak in a process meant to stay up."""
    registry = VoiceSessionRegistry()
    registry.open("session-1")

    registry.close("session-1")

    assert registry.interject("session-1", heard_seconds=1.0) is False


def test_opening_the_same_session_twice_replaces_the_first():
    """A reload should not leave an orphan nobody can reach."""
    registry = VoiceSessionRegistry()
    first = registry.open("session-1")
    second = registry.open("session-1")

    registry.interject("session-1", heard_seconds=1.0)

    assert second.cancelled is True
    assert first.cancelled is False


def test_a_later_report_that_knows_nothing_does_not_erase_the_timing():
    """One interruption, reported twice, by two things that know different amounts.

    The page has been playing the audio and says how far it got. The
    transcription service hears someone begin and can only say that it
    happened. Both land within a tenth of a second and in either order. If the
    one that knows nothing lands second and overwrites, the whole answer counts
    as heard and the next turn talks as if the person sat through it.
    """
    registry = VoiceSessionRegistry()
    token = registry.open("session-1")

    registry.interject("session-1", heard_seconds=2.4)
    registry.interject("session-1", heard_seconds=None)

    assert token.payload["heard_seconds"] == 2.4
