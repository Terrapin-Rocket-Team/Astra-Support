# Astra Support Contract v1

- Command surface is stable across repos: `astra-support init`, `astra-support test`, `astra-support hitl`.
- Consumer repos should expose `platformio.ini` at project root.
- Native test environment name should be `native`.
- Consumer CI should call the shared runner through `astra-support test --project .`.
- Mocks are provided by this repo as a PlatformIO library dependency.
