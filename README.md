# Astra-Support

Single-repo support platform for Astra-based projects.

Use this tool to prepare and validate a development checkout. It does not
replace the library documentation or prove that flight hardware works.

For the complete clean-machine sequence through Astra, Astra-Rocket,
Avionics/Airbrake, SITL, and HITL, start with the
[flight-software workflow](https://github.com/Terrapin-Rocket-Team/SRAD-Avionics/blob/main/docs/software-stack.md).

## What this repo provides

1. `astra-support` Python CLI for diagnostics, project sync, testing, and simulation.
2. `native-support/` PlatformIO-native mocks, shims, and Astra-specific test helpers.
3. `datasets/` flight and simulation assets included with CLI installations.

## Install CLI

Prerequisites:

- Git
- Python 3.10 or newer
- `pipx`
- `g++` for native builds and tests

On Ubuntu 24.04/WSL, install the prerequisites with:

```bash
sudo apt update
sudo apt install pipx g++
pipx ensurepath
```

Open a new terminal after `pipx ensurepath`, then install the CLI:

```bash
pipx install "git+https://github.com/Terrapin-Rocket-Team/Astra-Support.git@main"
```

Verify that the executable is available:

```bash
astra-support --version
```

This install now pulls all required Python dependencies (including PlatformIO,
NumPy/SciPy, Ambiance, pyserial, and matplotlib), so `pipx inject ...` is no longer
needed.

You still need `g++` on `PATH` for native build/test flows. `astra-support test`
and `astra-support sim --build` now run a preflight check and fail fast with
actionable errors if PlatformIO or `g++` is missing.

In interactive terminals, those commands can now offer to install missing tools
for you (PlatformIO + compiler) using available package managers.

To disable those prompts, set:

```bash
ASTRA_SUPPORT_DISABLE_INSTALL_ASSIST=1
```

## Core Commands

For an existing checkout, start with:

```bash
cd path/to/project
astra-support doctor --project .
astra-support test --project . --no-progress
```

`doctor` checks the local tooling and project configuration. `test` runs the
project's managed PlatformIO build/test matrix. Neither command uploads
firmware or performs hardware qualification.

```bash
astra-support doctor --project .
```

```bash
astra-support sync --project . --write-workflow
```

`sync` creates or refreshes:

- `.astra-support.yml`
- `.github/workflows/run_astra_support.yml`
- managed env blocks in `platformio.ini`
- packaged environment assets such as STM32 variants and linker scripts

Managed env snippets live in:

- `src/astra_support/assets/project/assets/envs/`

## Run Tests (consumer repo)

```bash
astra-support test --project .
```

The runner prepares PlatformIO dependencies serially, then builds environments
and test suites in parallel. Dependency preparation is cached until
`platformio.ini` or the selected environment set changes. Four workers is the
safe default; increase it on a high-memory machine with:

```bash
astra-support test --project . --jobs 8
```

Set `ASTRA_SUPPORT_JOBS` to choose a persistent local default. Use `--clean`
only when a real rebuild is needed; it clears both normal and parallel test
artifacts but does not silently update dependencies. Request updates explicitly:

```bash
astra-support test --project . --clean
astra-support test --project . --update-deps
```

`--no-install` skips dependency preparation when you know the checkout is
already ready. Transient PlatformIO system/file-lock errors are retried and the
reported retry includes the captured reason.

## Run Simulation Harness (consumer repo)

```bash
astra-support sim list --project ../Astra
```

```bash
astra-support sim run --project ../Astra --mode sitl --source physics
```

SITL reuses the existing native executable. If it is missing, Astra-Support
builds the `native` environment automatically. Pass `--build` when source or
configuration changes require an explicit incremental rebuild.

Set an Airbrake preflight target apogee before flight packets begin:

```bash
astra-support sim run --project ../Astra --mode sitl --source NyxORK --target-apogee 8200
```

```bash
astra-support sim run --project ../Astra --mode hitl --port COM3 --source physics
```

Project-specific custom simulators are supported by adding
`astra_support_sim.py` to the consumer project root (`--project` path) with:

- `create_data_source(source, project_root, astra_sim_module, args=None)` returning a
  DataSource instance or `None`
- optional `list_sim_sources(project_root, args=None)` for `astra-support sim list`

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

## Repo Layout

- `native-support/` contains the C++ PlatformIO support library
  shared by Astra's native tests. Its barometer mock supports both the legacy
  `update()` and time-aware `update(double currentTime)` interfaces while the
  Astra branches are consolidated.
- `src/astra_support/` contains the standalone Python CLI
- `datasets/` contains sim and flight assets that are bundled into CLI installations

## Development Checks

Create an isolated development environment and install this repository with its
dependencies:

```bash
python3 -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Or activate it in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then run the regression suite:

```bash
python -m pip install -e .
python -m unittest discover -v
```

The repository CI also installs the built package, exercises the CLI, and
verifies that `sync` can generate every supported environment and its packaged
STM32 assets.

## Use Native Support as a PlatformIO dependency

Add this to `lib_deps` in `platformio.ini`:

```ini
https://github.com/Terrapin-Rocket-Team/Astra-Support.git#main
```

## Notes

- `docs/support-contract-v1.md` defines the cross-repo convention.
- `docs/command-contract-v1.md` defines intended CLI usage and contributor expectations.
- `datasets/astra-rocket/manifest.yaml` tracks migrated datasets.
- Astra owns reusable library documentation; Astra-Rocket owns rocket behavior;
  SRAD-Avionics owns board-specific integration and handoff instructions.
