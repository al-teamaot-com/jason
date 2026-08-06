# INF-002 Production Readiness Bootstrap Gate

## Purpose

This control prevents a stateful dependency from being declared production-ready while a temporary bootstrap credential remains on the host.

## Rule

Outside explicit commissioning mode, production readiness is denied when `/etc/jason/openbao-bootstrap.token` exists.

Commissioning mode is a narrow temporary state used only while the runtime identity is being provisioned and verified. It must be explicitly requested with `--commissioning`; it is never inferred.

## Required behavior

The readiness closeout command must:

- fail closed when the bootstrap token exists and commissioning mode is not active;
- allow an explicit commissioning exception only with `--check-only`;
- never print, read, hash, copy, or otherwise expose the bootstrap token;
- report whether the bootstrap gate was bypassed by commissioning mode;
- preserve the recovery-readiness gate and all existing evidence controls.

## Production condition

A production-ready OpenBao host has:

- a valid dedicated orphan runtime token;
- no bootstrap token file;
- no temporary contract input file;
- verified recovery evidence;
- successful runtime health and contract checks.

## Safety boundary

This gate checks only file presence. It does not authenticate to OpenBao and does not inspect protected contents.
