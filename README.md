# Astra-Support

Shared support repo for Astra-based projects.

## What this repo provides

1. `astra-support` Python CLI (`init`, `test`, `sim`, `sitl`, `hitl`) for reusable local/CI workflows.
2. Native PlatformIO mocks/shims (migrated from `NativeTestMocks`) at repo root.
3. Shared simulation and flight datasets under `flight-data/`.

## Install CLI

```bash
pipx install "git+https://github.com/Terrapin-Rocket-Team/Astra-Support.git@main"
```

## Initialize a Consumer Repo

```bash
astra-support init --project . --write-workflow
```

This writes:
- `.astra-support.yml`
- `.github/workflows/run_unit_tests.yml`
- appends managed env blocks to `platformio.ini` for:
  - `native`
  - `teensy41`
  - `esp32s3`
  - `stm32h723vehx`
- copies required STM32H723 assets (`custom_variants/`, `ldscripts/`) when the STM32 env is included

Managed env snippets are file-based and editable in:

- `src/astra_support/templates/project/assets/envs/`

Choose envs explicitly (repeatable):

```bash
astra-support init --project . --env esp32s3 --env stm32h723vehx --env teensy41
```

## Run Tests (consumer repo)

```bash
astra-support test --project .
```

## Run Simulation Harness (consumer repo)

```bash
astra-support sitl --project ../Astra --source physics
```

```bash
astra-support sitl --project ../Astra --source NyxORK
```

```bash
astra-support sim --project ../Astra --mode hitl --port COM3 --source physics
```

Project-specific custom simulators are supported by adding
`astra_support_sim.py` to the consumer project root (`--project` path) with:

- `create_data_source(source, project_root, astra_sim_module, args=None)` returning a
  DataSource instance or `None`
- optional `list_sim_sources(project_root, args=None)` for `--list-sims`

Custom DataSource objects can also implement:

- `on_fc_telemetry(fields: dict[str, str])` to consume FC `TELEM/` values each lock-step cycle

Shortcut form:

```bash
astra-support sitl -C ../Astra -s NyxORK
astra-support test -C ../Astra -I -B -T -P
```

## CLI Self-Update Prompt

When run interactively, `astra-support` checks periodically for updates and can
prompt to install them before continuing.

- Skip once: `astra-support --no-update-check ...`
- Disable globally: set `ASTRA_SUPPORT_DISABLE_UPDATE_CHECK=1`
- Change check interval (seconds): `ASTRA_SUPPORT_UPDATE_CHECK_INTERVAL_SECONDS`

## Use Native Mocks as PlatformIO dependency

Add this to `lib_deps` in `platformio.ini`:

```ini
https://github.com/Terrapin-Rocket-Team/Astra-Support.git#main
```

## Notes

- `docs/support-contract-v1.md` defines the cross-repo convention.
- `docs/command-contract-v1.md` defines intended CLI usage and contributor expectations.
- `flight-data/astra-rocket/manifest.yaml` tracks migrated datasets.
