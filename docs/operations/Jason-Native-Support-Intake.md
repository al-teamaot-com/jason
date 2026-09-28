# Jason Native Support Intake

**Status:** Proposed for production activation  
**Owner:** Jason Architecture Authority  
**Scope:** Native host polling and durable intake of canonical Project Jason support defects  
**Canonical source:** Yes  
**Last reviewed:** 2026-09-28

## Purpose

Jason must discover Project Jason break/fix work even when no browser, ChatGPT
session, or human conversation is open.

The native support intake worker polls protected GitHub `main` directly from
the Jason host and derives the engineering queue from canonical `SUPPORT.md`.

It does not use ChatGPT tasks, browser automation, or a human workstation.

## Trigger

`jason-support-intake.timer` runs on the Jason Ubuntu host:

- 90 seconds after boot;
- every 2 minutes afterward;
- with a small randomized delay to avoid synchronized host work;
- persistently across reboot.

## Canonical input

Only `SUPPORT.md` from protected GitHub `main` is authoritative for intake.

Draft branches and unmerged support-list PRs are not actionable support work.

Rows whose status contains `Resolved`, `Closed`, or `Reclassified` are not
placed into the open engineering queue.

## Queue derivation

For each open support item, Jason records:

- support ID;
- priority;
- canonical status;
- title;
- first and last observation;
- any open PR that already references the support ID;
- work state.

Work states are:

- `active_engineering` — at least one open PR explicitly references the
  support item;
- `queued_for_engineering` — canonical support item exists but no active
  engineering PR is currently associated.

Within the same priority, active work remains selected before unstarted work so
Jason finishes what it began rather than thrashing between defects.

## Durable state

The worker writes only under:

`/var/lib/jason/openclaw/support-intake`

Artifacts:

- `support-work-queue.json`;
- `next-support-work.json`.

The files are mode 0600 and the directory is mode 0700.

## Authority boundary

Version 1 intake is read-only with respect to GitHub and provider systems.

It uses the existing authenticated `gh` installation on the Jason host only
to read protected-main `SUPPORT.md` and open PR metadata.

It does not:

- modify GitHub;
- create branches;
- edit source;
- open PRs;
- deploy;
- mutate provider systems;
- send Teams messages.

Those actions must occur through their own governed execution capabilities.

## Engineering executor

Native intake and autonomous source engineering are separate concerns.

The intake worker explicitly records:

`engineering_executor=not_configured`

until Jason has a governed repository-engineering executor.

This prevents the system from falsely claiming that support defects are being
repaired merely because they were detected and prioritized.

The intended completed workflow is:

```text
canonical SUPPORT.md entry
        |
        v
native support intake
        |
        v
governed repository-engineering executor
        |
        v
isolated branch / tests / PR
        |
        v
J-CHANGE-001 integration gates
        |
        v
J-CHANGE-002 autonomous repair classification
        |
        v
governed repair deployment
        |
        v
authoritative verification + support closure
        |
        v
one Teams completion message to person-al
        |
        v
next eligible support item
```

## Installation

After this source is merged into protected `main`, install from the exact
authoritative checkout:

```bash
cd /home/al/projects/jason
git fetch origin
git checkout main
git pull --ff-only
bash tools/install_jason_support_intake.sh
```

The installer creates the bounded state directory, installs the two systemd
units, enables the timer, runs an immediate intake pass, and verifies the
durable queue artifacts.

## Acceptance

Production acceptance requires:

1. `jason-support-intake.timer` is active;
2. closing the browser has no effect on the timer;
3. a canonical open support row appears in the local queue within one poll
   interval;
4. resolved/reclassified rows are excluded;
5. an open PR that references the support ID changes that item to
   `active_engineering`;
6. no GitHub/provider mutation occurs during intake;
7. the queue explicitly reports the engineering-executor state.

## Failure behavior

A GitHub read failure causes the service run to fail. The previous durable
queue remains intact and no support item is silently removed.

The worker never invents support items from local state when protected-main
evidence is unavailable.
