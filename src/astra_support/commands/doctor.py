from __future__ import annotations

from pathlib import Path

from ..config.support_file import load_support_config
from ..platformio.config import env_names
from ..prereqs import check_toolchain


def run(args) -> int:
    project_root = Path(args.project).resolve()
    issues: list[str] = []
    notes: list[str] = []

    if not project_root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_root}")

    config = load_support_config(project_root, args.config)
    config_path = config.path or (project_root / ".astra-support.yml")
    if config.path:
        notes.append(f"support config: {config.path}")
    else:
        notes.append(f"support config: not found ({config_path.name} optional)")

    platformio_path = project_root / "platformio.ini"
    if not platformio_path.exists():
        issues.append(f"Missing platformio.ini in {project_root}")
        discovered_envs: list[str] = []
    else:
        discovered_envs = env_names(platformio_path)
        notes.append(f"platformio envs: {', '.join(discovered_envs) if discovered_envs else 'none'}")

    dataset_roots = [project_root / "datasets", Path(__file__).resolve().parents[3] / "datasets"]
    available_dataset_roots = list(dict.fromkeys(str(path) for path in dataset_roots if path.exists()))
    if available_dataset_roots:
        notes.append(f"datasets: {', '.join(available_dataset_roots)}")
    else:
        issues.append("No datasets directory found in project or support repo.")

    custom_sim = project_root / "astra_support_sim.py"
    notes.append(f"custom sim hooks: {'present' if custom_sim.exists() else 'absent'}")

    toolchain = check_toolchain(require_platformio=True, require_cpp=True, offer_install=False)
    notes.extend(toolchain.notes)
    issues.extend(toolchain.errors)

    print(f"Doctor report for {project_root}")
    for note in notes:
        print(f"[ok] {note}")
    for issue in issues:
        print(f"[issue] {issue}")
    return 0 if not issues else 1
