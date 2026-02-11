# Astra-Support

Shared support repo for Astra-based projects.

## What this repo provides

1. `astra-support` Python CLI (`init`, `test`, `hitl`) for reusable local/CI workflows.
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

## Run Tests (consumer repo)

```bash
astra-support test --project .
```

## Run HITL/SITL Harness (consumer repo)

```bash
astra-support hitl --project . -- --mode sitl --source physics
```

## Use Native Mocks as PlatformIO dependency

Add this to `lib_deps` in `platformio.ini`:

```ini
https://github.com/Terrapin-Rocket-Team/Astra-Support.git#main
```

## Notes

- `docs/support-contract-v1.md` defines the cross-repo convention.
- `flight-data/astra-rocket/manifest.yaml` tracks migrated datasets.
