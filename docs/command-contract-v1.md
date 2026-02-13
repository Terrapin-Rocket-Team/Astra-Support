# Astra Support Command Contract v1

This document defines intended usage and contributor expectations for the
`astra-support` CLI while the repo is still evolving.

## Purpose

- Provide one shared CLI for Astra-family repos.
- Keep setup, testing, and simulation workflows consistent across repos.
- Favor practical automation over strict long-term API stability.

## Command Surface

These commands are the public contract:

- `astra-support init`
- `astra-support test`
- `astra-support sim`
- `astra-support sitl`
- `astra-support hitl`

Aliases like `harness`, `sim-sitl`, `serial`, `hw` are convenience only.
Contributors should treat primary command names above as canonical.

## Intended Uses

### `init`

Use for first-time repo bootstrap.

Expected responsibilities:

- create `.astra-support.yml`
- optionally create workflow yaml
- append missing managed envs to `platformio.ini`
- copy packaged env assets when needed

### `test`

Use for local/CI PlatformIO test orchestration.

Expected responsibilities:

- discover envs from `platformio.ini`
- install/update platform dependencies
- build envs
- run tests
- return non-zero exit code on failure

### `sim`

Use for full simulation harness access when mode is explicit.

Expected responsibilities:

- accept forwarded sim flags
- require `--mode` (`hitl` or `sitl`)
- run data source + link loop + reporting/logging
- optionally load project-local custom source hooks from
  `<project>/astra_support_sim.py`
- support optional custom source feedback hooks (`on_fc_telemetry`) so project
  simulators can react to FC telemetry in lock-step

### `sitl`

Use for SITL preset (same engine as `sim`, mode pinned to SITL).

Expected responsibilities:

- force `--mode sitl`
- support `--source physics|net|<csv>`
- auto-start native executable unless disabled

### `hitl`

Use for HITL preset (same engine as `sim`, mode pinned to HITL).

Expected responsibilities:

- force `--mode hitl`
- require serial port selection for actual run

## Flag and UX Contract

- Long flag names must stay clear and descriptive.
- One-character shortcuts are preferred for high-frequency workflows.
- `-h/--help` on wrapper commands shows wrapper help.
- Use `-- --help` to see forwarded simulation help:
  - `astra-support sitl -- --help`
  - `astra-support hitl -- --help`
  - `astra-support sim -- --help`

## Side-Effect Contract

By command:

- `init`: writes/updates config/workflow/env snippets/assets under target repo.
- `test`: writes build artifacts under target repo (`.pio/...`) and prints summary.
- `sim/sitl/hitl`: may write local sim logs (`sim_log_*.csv`) and SITL process logs
  (default `<project>/.pio_native_verbose.log`).

No command should silently edit unrelated files.

## Exit Code Contract

- `0`: success.
- non-zero: failure or unusable invocation (invalid args, missing requirements,
  runtime failures).

Exact non-zero code values may vary by subsystem; callers should treat any
non-zero as failure.

## Contributor Guardrails

When changing CLI behavior:

- Preserve canonical command names.
- Avoid moving side effects between commands.
- Update `README.md` and this contract in the same PR for behavior changes.
- Prefer additive changes to flags; if removing/changing semantics, document it
  clearly and bump version.
- Keep command handlers thin and push logic into subsystem modules.

## Current Non-Goals

- Strict semver-grade backward compatibility for every convenience alias.
- Comprehensive plugin architecture.
- Deep config schema management.

This repo is still maturing; speed and clarity are prioritized over heavy process.
