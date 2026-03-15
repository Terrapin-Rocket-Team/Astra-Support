from __future__ import annotations

import math

import matplotlib.pyplot as plt


def plot_history(history: dict[str, list], *, source_name: str) -> None:
    if not history["time"]:
        return

    sim_velocity = _derive_series_rate(history["time"], history["sim_alt"])
    sim_accel = history["sim_acc_mps2"]
    if not any(_is_number(value) for value in sim_accel):
        sim_accel = _derive_series_rate(history["time"], sim_velocity)

    fig, (ax_alt, ax_vel, ax_acc, ax_ctrl) = plt.subplots(4, 1, figsize=(12, 11), sharex=True)
    ax_alt.plot(history["time"], history["sim_alt"], label="Sim altitude", color="tab:blue")
    if any(_is_number(value) for value in history["fc_alt"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_alt"]], label="FC altitude", color="tab:orange")
    if any(_is_number(value) for value in history["fc_est_apogee_m"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_est_apogee_m"]], label="Pred apogee", color="tab:red")
    if any(_is_number(value) for value in history["fc_target_apogee_m"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_target_apogee_m"]], label="Target apogee", color="tab:purple")
    ax_alt.set_ylabel("Altitude (m)")
    ax_alt.grid(True, linestyle="--", alpha=0.3)

    if any(_is_number(value) for value in sim_velocity):
        ax_vel.plot(history["time"], [_nan_to_none(value) for value in sim_velocity], label="Sim velocity", color="tab:green")
    ax_vel.set_ylabel("Velocity (m/s)")
    ax_vel.grid(True, linestyle="--", alpha=0.3)

    if any(_is_number(value) for value in sim_accel):
        ax_acc.plot(history["time"], [_nan_to_none(value) for value in sim_accel], label="Sim accel", color="tab:purple")
    if any(_is_number(value) for value in history["fc_acc_z_mps2"]):
        ax_acc.plot(history["time"], [_nan_to_none(value) for value in history["fc_acc_z_mps2"]], label="FC accel", color="tab:orange")
    ax_acc.set_ylabel("Accel (m/s^2)")
    ax_acc.grid(True, linestyle="--", alpha=0.3)

    stage_changes = _stage_changes(history)
    for index, (timestamp, stage_value) in enumerate(stage_changes):
        label = "Stage change" if index == 0 else None
        for axis in (ax_alt, ax_vel, ax_acc, ax_ctrl):
            axis.axvline(timestamp, color="tab:gray", linestyle="--", linewidth=1.0, alpha=0.45, label=label if axis is ax_alt else None)
        ax_alt.annotate(
            str(stage_value),
            xy=(timestamp, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(2, -14),
            textcoords="offset points",
            rotation=90,
            va="top",
            ha="left",
            fontsize=8,
            color="tab:gray",
        )

    _show_legend_if_needed(ax_alt)
    _show_legend_if_needed(ax_vel)
    _show_legend_if_needed(ax_acc)

    if any(_is_number(value) for value in history["fc_flap_cmd_deg"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_flap_cmd_deg"]], label="Flap cmd", color="tab:green")
    if any(_is_number(value) for value in history["fc_flap_actual_deg"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_flap_actual_deg"]], label="Flap actual", color="tab:brown")
    if any(_is_number(value) for value in history["fc_mach"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_mach"]], label="Mach", color="tab:cyan")
    ax_ctrl.set_xlabel("Time (s)")
    ax_ctrl.set_ylabel("Control")
    ax_ctrl.grid(True, linestyle="--", alpha=0.3)
    _show_legend_if_needed(ax_ctrl)
    fig.suptitle(f"Astra Support Simulation: {source_name}")
    plt.tight_layout()
    plt.show()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def _nan_to_none(value):
    if _is_number(value):
        return value
    return None


def _stage_changes(history: dict[str, list]) -> list[tuple[float, object]]:
    changes: list[tuple[float, object]] = []
    last_stage = object()
    for timestamp, stage_value in zip(history.get("time", []), history.get("fc_stage", [])):
        if stage_value in ("", None, "unknown"):
            continue
        if stage_value != last_stage:
            changes.append((timestamp, stage_value))
            last_stage = stage_value
    return changes


def _derive_series_rate(time_values: list[float], sample_values: list[float]) -> list[float]:
    if not time_values or not sample_values:
        return []

    derived = [math.nan] * min(len(time_values), len(sample_values))
    for index in range(1, len(derived)):
        prev_time = time_values[index - 1]
        curr_time = time_values[index]
        prev_value = sample_values[index - 1]
        curr_value = sample_values[index]
        if not (_is_number(prev_value) and _is_number(curr_value)):
            continue
        dt = curr_time - prev_time
        if dt <= 0:
            continue
        derived[index] = (curr_value - prev_value) / dt

    if len(derived) > 1 and _is_number(derived[1]):
        derived[0] = derived[1]
    return derived


def _show_legend_if_needed(axis) -> None:
    handles, labels = axis.get_legend_handles_labels()
    if handles and labels:
        axis.legend(loc="best")
