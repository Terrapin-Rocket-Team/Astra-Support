# Astra Support Command Contract v1

This document defines intended usage and contributor expectations for the
`astra-support` CLI while the repo is still evolving.

## Purpose

- Provide one shared CLI for Astra-family repos.
- Keep setup, testing, and simulation workflows consistent across repos.
- Favor practical automation over strict long-term API stability.

## Command Surface

These commands are the primary public contract:

- `astra-support doctor`
- `astra-support sync`
- `astra-support test`
- `astra-support sim list`
- `astra-support sim run`

Compatibility aliases like `init`, `sitl`, and `hitl` may exist during
migrations. Contributors should treat the command names above as canonical.

## Intended Uses

### `sync`

Use for managed project bootstrap and refresh.

Expected responsibilities:

- create `.astra-support.yml`
- optionally create workflow yaml
- append missing managed envs to `platformio.ini`
- copy packaged env assets when needed

### `test`

Use for local/CI PlatformIO test orchestration.

Expected responsibilities:

- discover envs from `platformio.ini`
- validate required local toolchain before work starts:
  - PlatformIO CLI availability
  - C++ compiler availability for native/unix flows
- in interactive terminals, may offer automatic installation attempts for
  missing prerequisites using available package managers
- install/update platform dependencies
- build envs
- run tests
- return non-zero exit code on failure

### `doctor`

Use for preflight validation of project structure and local requirements.

Expected responsibilities:

- validate `platformio.ini`
- validate local toolchain availability
- report config, dataset, and custom sim discovery

### `sim run`

Use for full simulation harness access when mode is explicit.

Expected responsibilities:

- accept forwarded sim flags
- require `--mode` (`hitl` or `sitl`)
- run data source + link loop + reporting/logging
- when `--build` is used, validate PlatformIO CLI and C++ compiler before build
- in interactive terminals, may offer automatic installation attempts for
  missing prerequisites when `--build` is used
- optionally load project-local custom source hooks from
  `<project>/astra_support_sim.py`
- support optional custom source feedback hooks (`on_fc_telemetry`) so project
  simulators can react to FC telemetry in lock-step

### `sim list`

Use to discover bundled, local, and custom sim sources.

### `sitl`

Use only as a compatibility alias for `sim run --mode sitl`.

Expected responsibilities:

- force `--mode sitl`
- support `--source physics|net|<csv>`
- auto-start native executable unless disabled

### `hitl`

Use only as a compatibility alias for `sim run --mode hitl`.

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

- `sync`: writes/updates config/workflow/env snippets/assets under target repo.
- `test`: writes build artifacts under target repo (`.pio/...`) and prints summary.
- `sim run/sitl/hitl`: may write local sim logs (`sim_log_*.csv`) and SITL process logs
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
