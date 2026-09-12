# 7. Where a skill package comes from

Date: 2026-09-12

## Status

Accepted

## Context

ADR-0004 records what a skill package is made of and ADR-0006 records that a
package is mounted on a planning module at a fixed version. Neither says where
the files come from, and the first implementation answered that question in the
wrong place: the Playground could mount a package from a public git repository
at a pinned version, while the SDK took local paths only.

Five rules governed that fetch — only public `https` addresses, no login written
into the address, a version that must be given, a 5 MB ceiling, and the server's
own git configuration kept out of it. All five are facts about skill packages,
not about a website, yet all five lived in `playground/services/skill_store.py`.
Anyone building a workflow in Python got none of them, and the one place that
had them was the one place least able to state them as a standard.

The rules are also not a matter of taste. A package that follows its author's
latest commit changes an agent's behaviour without anyone mounting anything. An
address carrying a login is handed out with the agent to everyone who opens it.
A package is text, so a large download is a sign something else is being
carried. These hold wherever a package is mounted from.

## Decision

**Where a package may come from is part of the skill package format, so it lives
in `agentic_sdk.skills`.** The SDK resolves three kinds of source: a directory,
a zip archive, and a public git repository at a fixed version. The Playground
calls the same code and adds only what is its own — staging, the digest-keyed
store, the agent spec, and the wording shown to a person.

**One parameter takes them all.** `skill_packages` accepts a source or a list of
sources, each either a path or an address; a bare string is one source, not a
sequence of characters. Whatever the source, mounting ends at a directory on
this machine, and the caller never handles that path.

**An address carries its version.** `https://host/org/name.git@v1.2.0` names the
repository and the version in one string, because a source is one value and
splitting it into two parameters makes a version optional in practice. An
address without a version is refused.

**The five rules move with the code**: a public `https` address or a `file://`
repository on this machine and nothing else, no login in the address, a
version that is a tag, branch or commit name, 5 MB once unpacked, and git run
without the machine's own configuration or credential helpers. A refusal names
one rule and the source it applies to, the way a package refusal names one rule
and one file.

**A fetched package is kept.** The same address and version resolve to the same
directory, and a package already there is not fetched again, so a workflow that
has run once still starts when the network or the repository is gone. The
directory is under the user's cache, or wherever `AGENTIC_SDK_SKILL_PACKAGES`
points.

**Fetching happens when the package is mounted**, which is when the planning
module is built — not on a run. A workflow that starts does not stop later
because a repository moved.

## Consequences

- `agentic_sdk.skills` runs `git` as a subprocess and writes into a cache
  directory. Both are new for the SDK, and both happen only when a source that
  needs them is given; a directory path still costs neither.
- Building a planning module from an address does network I/O, so it can fail
  for reasons that have nothing to do with the package. The refusal says which
  of the two it was: `fetch_failed` names the address, and the package rules of
  ADR-0004 name a file.
- The Playground's own source checks are gone: it reports what the SDK refuses,
  translated into the wording a person reads.
- The Playground narrows the address rule to `https`, because its addresses are
  typed into a browser by someone it does not know. The SDK also reads a
  `file://` repository, which is a path on the machine doing the mounting.
- A private repository is still out of reach. Supporting one means holding a
  credential, which is a separate decision about where credentials live.
- ADR-0004 and ADR-0006 stand unchanged; this ADR answers a question neither of
  them asked.
