# Astra Support Contract v1

- Command surface is owned by the CLI and currently centers on `astra-support doctor`, `astra-support sync`, `astra-support test`, and `astra-support sim ...`.
- Consumer repos should expose `platformio.ini` at project root.
- Native test environment name should be `native`.
- Consumer CI should call the shared runner through `astra-support test --project .`.
- Native support helpers are provided by this repo as a PlatformIO library dependency.
