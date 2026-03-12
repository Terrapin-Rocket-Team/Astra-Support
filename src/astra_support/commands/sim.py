from __future__ import annotations

from pathlib import Path

from ..config.support_file import load_support_config
from ..sim.session import run_simulation
from ..sim.sources import invoke_hook, list_available_sources, load_custom_sim_hooks


def list_sources(args) -> int:
    project_root = Path(args.project).resolve()
    config = load_support_config(project_root, args.config)
    sources = list_available_sources(project_root, extra_roots=config.dataset_paths)
    _, custom_list_fn = load_custom_sim_hooks(project_root)
    if custom_list_fn is not None:
        custom_sources = invoke_hook(
            custom_list_fn,
            {"project_root": project_root, "args": args},
            [project_root, args],
        ) or []
        sources.extend(str(item) for item in custom_sources)
    if not sources:
        print("No simulation sources found.")
        return 1
    print("Available simulation sources:")
    for source in sorted(dict.fromkeys(sources)):
        print(f"- {source}")
    return 0


def run(args) -> int:
    project_root = Path(args.project).resolve()
    config = load_support_config(project_root, args.config)
    if not getattr(args, "port", None) and config.hitl_port and args.mode == "hitl":
        args.port = config.hitl_port
    if not getattr(args, "sitl_exe", None) and config.sitl_exe:
        args.sitl_exe = config.sitl_exe
    if not getattr(args, "dataset_root", None) and config.dataset_paths:
        args.dataset_root = list(config.dataset_paths)
    return run_simulation(args, project_root)
