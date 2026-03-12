from __future__ import annotations


def parse_telem_header(header_line: str) -> tuple[dict[str, int] | None, list[str] | None]:
    if not header_line.startswith("TELEM/"):
        return None, None
    parts = [part.strip() for part in header_line[6:].strip().split(",")]
    return {name: index for index, name in enumerate(parts)}, parts


def extract_fc_fields(current_values: list[str], fc_col_map: dict[str, int] | None) -> dict[str, str]:
    if not fc_col_map:
        return {}
    return {
        key: current_values[index]
        for key, index in fc_col_map.items()
        if index < len(current_values)
    }
