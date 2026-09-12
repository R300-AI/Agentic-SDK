# 4. What a skill package is made of

Date: 2026-09-10

## Status

Accepted. One rule below — refusing a package for a file no skill uses — was
withdrawn by ADR-0006, which also moved skills onto the planning module.

## Context

Agents get skills the way Claude Code and Codex do: a person selects one with
`/`, or the planning module picks one by its description, and its content joins
the conversation. Both of those tools follow the open Agent Skills format — a
directory with a `SKILL.md` whose frontmatter carries a name and a description.

That format leaves two things open that matter here. A skill names the other
files it relies on inside its prose, so anything that needs the full set of
files has to read the prose to find them, and two such readers can disagree
about what a skill includes. And a skill may bundle scripts; a package installed
into the Playground would then run code nobody reviewed on the server.

A third constraint is ours alone: modules cannot open files during a run.
Whatever a skill relies on has to be handed in at once, so the full set of files
has to be known before the turn starts.

## Decision

**The skill body stays in the open format.** Each skill is a `SKILL.md` with its
name and description in the frontmatter. The name and description are recorded
there and nowhere else.

**A package adds one mapping file.** It records, for each skill, which
instructions and which prompts it uses and in what order, and who maintains the
package and how to reach them. It does not record a version; the version is the
tag or commit the package is mounted at.

**A package holds text only.** Nothing in it is executed.

**Mounting refuses a package** when any of these hold:

- it contains anything other than text;
- the mapping file refers to a file that does not exist;
- a file among the instructions or prompts is used by no skill;
- a skill's directory name, its `SKILL.md` name and its entry in the mapping
  file do not all agree;
- a skill name is already taken in the project;
- a description is longer than 1,024 characters;
- a skill's inserted content exceeds the limit set for the models the agent is
  bound to.

## Consequences

- A skill written here runs in Claude Code and Codex unchanged, provided its
  frontmatter uses only fields the open format defines. A skill from those tools
  can be mounted here once a mapping file is written for it.
- Nothing finds a skill's files by reading its prose. The mapping file is the
  only record of what a skill uses.
- Work that needs code reaches the agent through a module, such as tool calling,
  not through a skill.
