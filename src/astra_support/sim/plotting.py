from __future__ import annotations

import math

import matplotlib.pyplot as plt


def plot_history(history: dict[str, list], *, source_name: str) -> None:
    if not history["time"]:
        return

    fig, (ax_alt, ax_ctrl) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax_alt.plot(history["time"], history["sim_alt"], label="Sim altitude", color="tab:blue")
    if any(_is_number(value) for value in history["fc_alt"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_alt"]], label="FC altitude", color="tab:orange")
    if any(_is_number(value) for value in history["fc_est_apogee_m"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_est_apogee_m"]], label="Pred apogee", color="tab:red")
    if any(_is_number(value) for value in history["fc_target_apogee_m"]):
        ax_alt.plot(history["time"], [_nan_to_none(value) for value in history["fc_target_apogee_m"]], label="Target apogee", color="tab:purple")
    ax_alt.set_ylabel("Altitude (m)")
    ax_alt.grid(True, linestyle="--", alpha=0.3)
    ax_alt.legend(loc="best")

    if any(_is_number(value) for value in history["fc_flap_cmd_deg"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_flap_cmd_deg"]], label="Flap cmd", color="tab:green")
    if any(_is_number(value) for value in history["fc_flap_actual_deg"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_flap_actual_deg"]], label="Flap actual", color="tab:brown")
    if any(_is_number(value) for value in history["fc_mach"]):
        ax_ctrl.plot(history["time"], [_nan_to_none(value) for value in history["fc_mach"]], label="Mach", color="tab:cyan")
    ax_ctrl.set_xlabel("Time (s)")
    ax_ctrl.set_ylabel("Control")
    ax_ctrl.grid(True, linestyle="--", alpha=0.3)
    ax_ctrl.legend(loc="best")
    fig.suptitle(f"Astra Support Simulation: {source_name}")
    plt.tight_layout()
    plt.show()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def _nan_to_none(value):
    if _is_number(value):
        return value
    return None
