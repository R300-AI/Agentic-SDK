# 6. Skills belong to the planning module

Date: 2026-09-12

## Status

Accepted

## Context

A skill is a named procedure for one kind of task: the steps to take and the
format the result must follow. A person calls one up with `/` in the Runner.

The first implementation mounted skills on the workflow: `Workflow` took
`skill_packages`, `run()` took the skill's name, and the chosen skill's text was
folded into the conversation by rewriting the metadata of the latest user turn.
Three things are wrong with that.

**The workflow would have to know what a skill is.** Every module would then be
rewritten to read the skill, or the workflow itself would need a model to decide
which skill fits. Model inference belongs to a module, not to the object that
wires modules together.

**It rewrote a turn that had already happened.** ADR-0002 records that a
conversation is appended to and never revised; the skill text arrived by editing
the stored user turn.

**It duplicated a decision that now has a home.** ADR-0005 made planning a stop
every run passes through, and gave it the decision about what happens next.
Which procedure this turn follows is that same kind of decision.

Practice elsewhere was surveyed before deciding. The Agent Skills standard
(agentskills.io), Claude Code and Codex all load a skill in stages: name and
description at startup, the body word for word when the skill is taken up,
bundled files only when read. None of them summarises or rewrites a skill's
body. OpenAI's skills tool states that skill instructions are user prompt input
and not system prompt input. None of them limits a conversation to one skill.
All of them bound the listing: Codex gives it 2% of the context window, or 8,000
characters when that is unknown; Claude Code caps each entry at 1,536
characters. Extra files in a skill folder are allowed everywhere.

A prototype settled the remaining question — whether a model should summarise a
skill before the action module sees it. Kept at tag
`archive/skill-brief-prototype` (commit 57cf7de), five runs each of verbatim and
summarised, one transcript, one
model: both kept the skill's format every time, and the "summary" came out
longer than the source it replaced (266 characters against 260), because the
model copied the fixed format word for word. Summarising bought nothing and
added a model call that can fail.

## Decision

**Skills are mounted on a planning module.** `NextStepWithSkills` extends
`NextStepPlan` and holds the packages. `Workflow` knows nothing about skills,
and no other module changes.

**A skill's content passes word for word.** Nothing summarises or rewrites it.

**A skill taken up joins the conversation as a turn of its own**, in the
person's role rather than the system's, labelled with the skill's name. A skill
package can come from anywhere; its text does not get the authority of the
agent's own configuration. Earlier turns are never rewritten, so ADR-0002 holds.
The content stays in the conversation for the rest of it, and the planning
module does not read the package again on later turns.

**A conversation may take up more than one skill.** Every visit to planning sees
the full listing — each skill's name and description — with the ones already
taken up marked.

**The listing is bounded**: 8,000 characters in all, each description cut to
1,536 characters in the listing; a single skill's content is capped at 20,000
characters. Over the budget, descriptions are cut first and whole entries are
dropped last, and the trace says how many were dropped.

**A package may withhold a skill from the agent's own choosing.** That
declaration lives in the package's mapping file, not in `SKILL.md`, so
`SKILL.md` keeps only the six fields the Agent Skills standard defines and a
skill written for another tool loads unchanged.

**A package with files no skill uses is no longer refused.** The rule was meant
to stop a package smuggling material nobody reads; the text-only rule and the
size caps already do that, while this one refused any repository carrying a
README. The remaining checks from ADR-0004 stand.

**In the Builder**, a step of its own asks whether the agent has a standard
operating procedure to follow, and only then shows the mounting controls. An
agent with a package mounted plans with a model, whatever it answered about what
to do when it is unsure. The Runner's `/` menu reads the agent's spec and the
package store, not a built workflow, because the menu opens before any run
starts.

## Consequences

- The workflow's skill API goes: `skill_packages`, the skill argument to `run()`,
  and the memory method that rewrote the latest user turn along with the turn
  metadata it wrote.
- Once a skill is taken up, its text is part of the conversation and costs input
  tokens on every later turn. A person who takes up several skills pays for all
  of them.
- An agent that answered 先停下來，交給人確認 and mounts a package now needs a
  model for planning, which it did not before.
- ADR-0004 stands except for the unused-file rule.
- Three alternatives were rejected: keeping skills on the workflow (the context
  above), summarising the skill with a model (the prototype), and giving the
  skill's text the system role (it would outrank the agent's own configuration).

## The implementation this replaces

The first skill implementation is kept at tag `archive/skill-system`, whose tip
is `70c675f` (preceded by `7d9bcd7`); the branch of that name is gone. There
skills were mounted on the workflow: `Workflow` took `skill_packages`, `run()`
took a `skill` argument, and the skill's text rewrote the latest user turn. It
is superseded by this ADR and is kept only as a record of how the question was
first answered; nothing should be developed from it. What is still in use — the package format of ADR-0004, the
package store, and the Builder and Runner controls — has been carried onto the
main line, so the branch holds no unique working code.
