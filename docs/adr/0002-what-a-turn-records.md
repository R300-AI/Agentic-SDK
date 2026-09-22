# 2. What a turn records

Date: 2026-09-05

## Status

Accepted, and extended by ADR-0008. An interruption during a long answer
reaches the run while it is still going, which this decision did not expect, so
the trim happens in two places for two moments: inside the run when the
interruption gets there, and on the Playground's own record when it arrives
after. What a turn records, and what the core is allowed to know, stand as
written.

## Context

The core promises to remember the conversation. It does not: it remembers what
the model produced. Those differ whenever an answer is cut short, and the
difference is not a voice problem. Interrupting a plain text stream, with no
audio anywhere near it:

```
使用者在畫面上已經看到 8 個字
記憶裡的助理回合：（一則都沒有）
```

The person read half a sentence and the record says the turn never happened.
Voice only made this visible, because the gap between produced and received is
seconds wide when speech is involved rather than milliseconds.

Two facts shaped what follows.

The first is where playback lives. ADR-0001 put audio in the Playground, so the
browser is what plays the answer and the browser is the only thing that knows
how much of it was heard. Measured against the real deployments, the run
finished 3ms after the audio did — which is to say the two are a race, and
whether the workflow is still alive when someone interrupts depends on how long
the answer was against how long the reflect module took.

The second is that memory is an extension point. `InContextMemory` exists
today; cross-context memory is on the roadmap and already visible as a locked
choice in the Builder; hierarchical memory follows. Every kind implements the
same `MemoryStore` protocol.

## Decision

**A turn records what was delivered to the person, and only the deliverer says
what that was.** The core never infers it from a stream's length or from
elapsed time.

**`WorkflowState` carries delivered content, and it is channel-neutral.** Token
deltas accumulate into it as they are emitted, so a text stream needs nothing
from its caller. Only the answering module's plain deltas count. A plan and a
check stream raw JSON to a trace panel, and that reaches nobody as an answer;
a two-channel answer streams its own envelope, and the field names and the
display channel are not what anyone heard. Whoever wires the modules together
names the deliverer, and whoever streams an envelope reports delivery outright. An audio transport reports as it plays. The word "spoken" does
not appear: the core does not know a speaker exists, which is ADR-0001's rule
and the reason `report_spoken_progress` and `spoken_so_far` are removed.

**The core does not wait for delivery.** Blocking a run until a browser
finishes playing would make the workflow's duration depend on an external
timeline, and the same rule that keeps microphones out of the core keeps
playback out of its clock.

**`MemoryStore`'s contract does not change.** Revising a past turn is not
something every kind of memory can honour: an append-only cross-context store
has no such operation, and a hierarchical store may have folded the turn into a
summary already. The core may only require of an extension point what every
implementation can do.

**A correction that arrives after the run belongs to whoever owns the
conversation record**, which is the caller. In the Playground that is
`RunnerConversationState`, which already holds the turns and builds a fresh
memory for each run — so the Playground trims its own record and the next run
is built from the corrected one.

## Consequences

The text-stream hole closes with no change to memory at all, because for text
and for desktop audio the delivery is settled before the run ends. Only browser
playback finishes late, and that case never reaches the core.

Each kind of memory decides how to fold in a correction. A hierarchical store
might apply it during consolidation; an event-sourced one might record it as an
event. The core does not dictate, which is what keeps the protocol small enough
for the kinds that do not exist yet.

The glossary gains **delivered content** for the channel-neutral concept, and
keeps **heard duration** for the audio-specific measurement that the audio layer
converts into it. The two are not synonyms: one is what reached the person, the
other is how long a speaker ran.

One consequence is named here and not resolved: reflect now runs after the
answer has been spoken aloud. Checking a sentence that is already in someone's
ears cannot unsay it. That belongs to the five-role promise rather than to
voice, and voice only made it visible.
