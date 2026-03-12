from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def source_kind(source_text: str) -> str:
    token = source_text.strip().lower()
    if token in {"physics", "phys", "p"}:
        return "physics"
    if token in {"net", "network", "udp"}:
        return "net"
    return "csv"


def list_available_sources(project_root: Path, *, extra_roots: list[str] | None = None) -> list[str]:
    roots = _candidate_roots(project_root, extra_roots)
    sources: set[str] = {"physics", "net"}
    for root in roots:
        if not root.exists():
            continue
        for csv_path in root.rglob("*.csv"):
            sources.add(csv_path.stem)
    return sorted(sources)


def resolve_csv_source(source_text: str, project_root: Path, *, extra_roots: list[str] | None = None) -> Path:
    requested = Path(source_text.strip().strip('"').strip("'"))
    for candidate in _direct_path_candidates(requested, project_root):
        if candidate.is_file():
            return candidate.resolve()

    matches: list[Path] = []
    for root in _candidate_roots(project_root, extra_roots):
        if not root.exists():
            continue
        for csv_path in root.rglob("*.csv"):
            if requested.name.lower() == csv_path.name.lower() or requested.stem.lower() == csv_path.stem.lower():
                matches.append(csv_path.resolve())

    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        raise ValueError("Source is ambiguous:\n  - " + "\n  - ".join(str(path) for path in unique[:10]))
    raise ValueError(f"Could not resolve CSV source '{source_text}'.")


def load_custom_sim_hooks(project_root: Path):
    module_path = project_root / "astra_support_sim.py"
    if not module_path.is_file():
        return None, None

    module_name = f"astra_support_custom_sim_{abs(hash(str(module_path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    create_fn = getattr(module, "create_data_source", None)
    list_fn = getattr(module, "list_sim_sources", None)
    if create_fn is not None and not callable(create_fn):
        raise TypeError(f"{module_path}: create_data_source must be callable")
    if list_fn is not None and not callable(list_fn):
        raise TypeError(f"{module_path}: list_sim_sources must be callable")
    return create_fn, list_fn


def invoke_hook(func, available_kwargs: dict[str, object], positional_fallback: list[object]):
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params):
        return func(**available_kwargs)

    keyword_candidates = [
        param.name
        for param in params
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    if keyword_candidates:
        kwargs = {name: available_kwargs[name] for name in keyword_candidates if name in available_kwargs}
        required = [
            param.name
            for param in params
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and param.default is inspect._empty
        ]
        if all(name in kwargs for name in required):
            return func(**kwargs)

    positional_count = len(
        [param for param in params if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    )
    return func(*positional_fallback[:positional_count])


def _candidate_roots(project_root: Path, extra_roots: list[str] | None) -> list[Path]:
    roots = [
        repo_root() / "datasets",
        project_root / "datasets",
        project_root / "flight-data",
    ]
    for root in extra_roots or []:
        roots.append((project_root / root).resolve() if not Path(root).is_absolute() else Path(root))
    return roots


def _direct_path_candidates(requested: Path, project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if requested.is_absolute():
        candidates.append(requested)
    else:
        candidates.extend(
            [
                Path.cwd() / requested,
                project_root / requested,
                repo_root() / requested,
            ]
        )
        if requested.suffix.lower() != ".csv":
            csv_path = requested.with_suffix(".csv")
            candidates.extend(
                [
                    Path.cwd() / csv_path,
                    project_root / csv_path,
                    repo_root() / csv_path,
                ]
            )
    return candidates
