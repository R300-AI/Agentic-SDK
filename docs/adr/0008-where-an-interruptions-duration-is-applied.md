# 8. Where an interruption's duration is applied

Date: 2026-09-13

## Status

Accepted. Extends ADR-0002, which placed the correction but left one of the
two cases unowned.

## Context

ADR-0002 settled what a turn records: what was delivered, as reported by
whoever delivered it. It expected browser playback to finish after the run had
ended, and placed the correction with whoever owns the conversation record —
in the Playground, `RunnerConversationState`.

Measured on the deployment, both halves of that expectation are wrong in part.

An interruption during a long answer arrives while the run is still going. The
page reports how long it had been playing on the socket that is already open
for the microphone, and that report stops the run. Every interruption measured
against a long answer landed this way, and the run ended as interrupted because
of it. For this case the correction is not late at all: it is the same event as
the interruption, and it arrives before the turn has been recorded.

An interruption during a short answer arrives after the run has ended, because
an answer is produced in seconds and takes far longer to say. There is then no
run to stop, and the turn is already stored whole.

Neither case was trimming anything. The in-run case reached a loop that watches
the audio go out piece by piece, and a browser plays its own audio, so the loop
saw nothing and the whole answer was recorded as delivered. The after-the-run
case had the mechanism ADR-0002 called for, and nothing ever called it: the
stored answer came straight from the run. Someone who heard 2.4 seconds had all
144 characters recorded as if they had sat through them.

## Decision

**Two moments, two owners, one rule.**

**An interruption that reaches the run is applied by the run.** Whoever
delivers reports what they handed over and leaves behind a way to answer how
much of it landed, given whatever the interruption reported about itself. The
engine asks that question at the moment it stops, and records the answer.

**An interruption that arrives after the run is applied by whoever owns the
record**, as ADR-0002 said. The server has nothing left to stop and no way to
know how far playback got, so it tells the page so, with the duration the page
itself reported; the page then asks for the stored turn to be trimmed. Both
writes to the conversation go in the order they were issued, so a correction
never lands on the turn before the one it belongs to.

**The core holds the question and never the arithmetic.** It knows a delivery
may have been cut short and that only the deliverer can say by how much.
Characters per second stay in the audio layer, so ADR-0001's rule — the core
does not know a speaker exists — is unchanged. The Playground applies the same
audio-layer rule to its own record rather than a second copy of it.

**Whoever asked for the stop is the authority on it.** A stream that notices
the flag reports how much it had produced; the person reports how long they had
been listening. The second stands where they disagree, and a key reported as
nothing is not a report at all.

**A turn that was cut off is marked as cut off**, so the next turn is built
from a record that does not look complete.

## Consequences

The engine checks for a cancellation after its last module as well as before
each one. Without that, an interruption arriving while the final module runs
has no later visit to be noticed at, and the turn is filed as finished.

A duration that never reaches either owner leaves the answer whole. Unknown is
not nought, and trimming to nothing would erase an answer the person did hear.

`delivered_so_far` and `interrupt_payload["delivered"]` are no longer the same
string on an interrupted turn: the first is what was handed over, the second is
what landed. The conversation keeps the second.

A page that is closed between the answer and the interruption never sends the
correction, and the record keeps the whole answer. Nobody is left to be
confused by it, and the alternative is a server guessing at a duration it
cannot observe.
