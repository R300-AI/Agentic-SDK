# 5. Every run closes the loop through planning

Date: 2026-09-11

## Status

Accepted

## Context

The SDK follows Generative Agents (Park et al., 2023): decision-making as a
loop in which an agent perceives, plans, retrieves and acts, while memory keeps
what happened in between. The code had drifted from that loop in two places.

**A workflow could run without planning.** `Workflow.plan` defaulted to nothing,
perception handed straight to retrieval, and every retrieve module handed
straight to action. Eleven of the seventeen test files that build a workflow,
and the tutorial that watches one run, never give it a planning module. The
Builder installs one only when Q5 is answered 再查一次再回答.

**Reflect ran after every action.** Whenever a reflect module was mounted, the
workflow sent it the action's result. That is not the paper's reflection, which
turns accumulated observations into higher-level memories when their importance
crosses a threshold — in practice two or three times a simulated day (§4.2). The
built-in modules came from Reflexion and CRITIC instead: check an answer after
producing it. Checking after acting carries the cost ADR-0002 left open: a
spoken answer is checked after the person has heard it.

Three other shapes were considered and rejected:

- *Keep action → reflect, and give only skill workflows a planning-controlled
  loop.* Two routing rules would coexist, and the gap in ADR-0002 would stay.
- *Send every action back through perception and planning inside the run.* An
  action changes things outside the run. Confirming it inside the run means the
  SDK decides when the world has settled, which is the caller's call, and it
  costs at least one more planning call on every turn.
- *Have planning declare in advance whether the run returns after acting.* It
  adds a flag with no use the caller cannot already get by starting the next
  turn, and it takes that decision away from them.

## Decision

**Every workflow has a planning module.** When none is given, `PassThroughPlan`
plans by a fixed rule and calls no model: retrieve if a retrieve module is
mounted, send the result to reflect once if a reflect module is mounted, then
act.

**A run is perceive, plan, and act.** Perception hands over to planning.
Planning chooses among retrieve, reflect and action, and nothing else. Retrieval
and reflect both hand back to planning. The action ends the run.

**Nothing inspects an action inside the run.** Whoever starts the next turn — a
person, or a script they wrote — observes what the action did, and that
observation is perception. An action that fails ends the run and reports the
error to the caller.

**Reflect is a stop planning uses, not a verdict on the answer.** Planning sends
work there and always gets the result back; what a reflect module does is its
own business. Planning and reflect exchange at most five times, after which
planning may only retrieve or act. `on_failure` is removed, because reflect no
longer decides where the run goes.

The built-in reflect modules confirm that planning and retrieval did their jobs:

- `EvidenceCheckReflect` reports a lookup that found nothing.
- `ResponseCheckReflect` becomes `PlanCheckReflect`, which uses a model to
  confirm that the plan's decision can be carried out — for example, that a
  skill it chose exists.

`NextStepPlan` gains `reflect_description`, the counterpart of
`retrieve_description`, so its model knows what the mounted reflect module is
for.

**In the Builder**, 再查一次再回答 installs `NextStepPlan` and allows one
return to retrieval. 先停下來，交給人確認 installs `PassThroughPlan`, and the
handoff message comes from what reflect reported rather than from which module
is mounted. An agent that retrieves nothing and answers 先停下來 mounts no
reflect module: a fixed rule makes no decision that can go wrong, and there is
no lookup to confirm. Exported code always names its planning module.

This ships as 0.3.0, without deprecation aliases.

## Consequences

- ADR-0002's open consequence no longer arises: reflect never follows the
  action, so no spoken sentence is checked after it has been heard.
- A workflow on `NextStepPlan` calls its model once more after every
  retrieval. A workflow on `PassThroughPlan` pays nothing for the extra stop.
- Code written for 0.2 breaks in four places: `on_failure`, the
  `ResponseCheckReflect` name, retrieval handing straight to action, and a
  workflow with no planning module. README, module docs and tutorials change
  with them.
- For an agent that retrieves nothing, Builder Q5 now only chooses whether
  planning uses a model.
- Reflect keeps its name in both languages. The paper's memory-building
  reflection is something a developer can put in that stop; the SDK does not
  ship one.
