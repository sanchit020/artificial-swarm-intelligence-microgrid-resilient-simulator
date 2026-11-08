"""Python/Streamlit adapter for the compiled C++ ASI simulation engine.

All optimization, decentralized multi-agent coordination, ACO rerouting,
PSO dispatch, battery accounting, and DC power-flow allocation execute in C++.
Python only serializes settings, supplies topology metadata, and loads results.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import tempfile

import pandas as pd

from .network_flow import consumer_feeder_edges


@dataclass
class Settings:
    demand_scale: float = 1.0
    solar_scale: float = 1.0
    wind_scale: float = 1.0
    hydro_scale: float = 1.0
    hydro_capacity: float = 40.0
    generator_capacity: float = 175.0
    battery_capacity: float = 160.0
    battery_power: float = 50.0
    initial_soc: float = 80.0
    reserve_soc: float = 25.0
    charge_efficiency: float = 0.94
    discharge_efficiency: float = 0.94
    substation_storage_capacity: float = 15.0
    substation_storage_power: float = 6.0
    generator_cost: float = 115.0
    battery_wear_cost: float = 8.0
    unserved_penalty: float = 18000.0
    reserve_penalty: float = 350.0
    generations: int = 3
    population: int = 8
    seed: int = 2026

    # Physical constraints & Swarm parameters
    generator_ramp_limit: float = 35.0
    battery_degradation_cost: float = 2.5
    pso_particles: int = 12
    pso_iterations: int = 10
    aco_ants: int = 10
    aco_evaporation: float = 0.15
    dispatch_mode: str = "swarm"  # "swarm" (Decentralized ASI) or "centralized" (Baseline)


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def _engine_path():
    candidates = [BUILD / "asi_engine.exe", BUILD / "Release" / "asi_engine.exe", BUILD / "asi_engine"]
    for p in candidates:
        if p.exists():
            return p
    BUILD.mkdir(exist_ok=True)
    try:
        subprocess.run(["cmake", "-S", str(ROOT), "-B", str(BUILD)], check=True, capture_output=True, text=True)
        subprocess.run(["cmake", "--build", str(BUILD), "--config", "Release", "--parallel"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise RuntimeError("Could not build the C++ ASI engine. Install CMake and a C++17 compiler, then run build_cpp.bat.\n" + detail) from exc
    for p in candidates:
        if p.exists():
            return p
    found = list(BUILD.rglob("asi_engine.exe")) + list(BUILD.rglob("asi_engine"))
    if found:
        return found[0]
    raise RuntimeError("CMake completed but asi_engine executable was not found in build/.")


def _write_config(path, settings, seed, mode, actions, line_overrides, substation_overrides, feeder_overrides, dispatch_mode=None):
    mode_str = dispatch_mode or getattr(settings, "dispatch_mode", "swarm")
    pairs = {
        "mode": mode,
        "dispatch_mode": mode_str,
        "seed": int(settings.seed if seed is None else seed),
        "demand_scale": settings.demand_scale,
        "solar_scale": settings.solar_scale,
        "wind_scale": settings.wind_scale,
        "hydro_scale": getattr(settings, "hydro_scale", 1.0),
        "hydro_capacity": getattr(settings, "hydro_capacity", 60.0),
        "generator_capacity": settings.generator_capacity,
        "battery_capacity": settings.battery_capacity,
        "battery_power": settings.battery_power,
        "initial_soc": settings.initial_soc,
        "reserve_soc": settings.reserve_soc,
        "sub_storage_capacity": getattr(settings, "substation_storage_capacity", 15.0),
        "sub_storage_power": getattr(settings, "substation_storage_power", 6.0),
        "charge_efficiency": settings.charge_efficiency,
        "discharge_efficiency": settings.discharge_efficiency,
        "generator_cost": settings.generator_cost,
        "battery_wear_cost": settings.battery_wear_cost,
        "unserved_penalty": settings.unserved_penalty,
        "reserve_penalty": settings.reserve_penalty,
        "population": settings.population,
        "generations": settings.generations,
        "generator_ramp_limit": getattr(settings, "generator_ramp_limit", 35.0),
        "battery_degradation_cost": getattr(settings, "battery_degradation_cost", 2.5),
        "pso_particles": getattr(settings, "pso_particles", 12),
        "pso_iterations": getattr(settings, "pso_iterations", 10),
        "aco_ants": getattr(settings, "aco_ants", 10),
        "aco_evaporation": getattr(settings, "aco_evaporation", 0.15),
    }
    lines = [f"{k}={v}" for k, v in pairs.items()]
    if actions is None:
        actions = [0] * 24
    if len(actions) != 24:
        raise ValueError("Exactly 24 battery actions are required.")
    if any(int(a) not in (-2, -1, 0, 1, 2) for a in actions):
        raise ValueError("Battery actions must be -2, -1, 0, 1, or 2.")
    lines.append("actions=" + ",".join(map(str, map(int, actions))))
    for (u, v), cap in (line_overrides or {}).items():
        lines.append(f"line_override={u},{v},{float(cap)}")
    for sub, cap in (substation_overrides or {}).items():
        lines.append(f"sub_override={sub},{float(cap)}")
    for (u, v), cap in (feeder_overrides or {}).items():
        lines.append(f"feeder_override={u},{v},{float(cap)}")
    for (u, v), cap in consumer_feeder_edges().items():
        lines.append(f"feeder={u},{v},{float(cap)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _invoke(settings, seed=None, actions=None, mode="simulate", line_capacity_overrides=None,
            substation_capacity_overrides=None, feeder_capacity_overrides=None, dispatch_mode=None):
    engine = _engine_path()
    with tempfile.TemporaryDirectory(prefix="asi_cpp_") as td:
        td = Path(td)
        cfg = td / "config.txt"
        hourly_path = td / "hourly.csv"
        summary_path = td / "summary.txt"
        messages_path = td / "messages.csv"

        _write_config(cfg, settings, seed, mode, actions, line_capacity_overrides,
                      substation_capacity_overrides, feeder_capacity_overrides, dispatch_mode)

        proc = subprocess.run([str(engine), str(cfg), str(hourly_path), str(summary_path), str(messages_path)],
                              cwd=str(ROOT), capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"C++ ASI engine failed (exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}")

        hourly = pd.read_csv(hourly_path)
        summary = {}
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                summary[k] = v

        chosen = [int(x) for x in summary.pop("actions", "0").split(",")]
        result = {}
        for k, v in summary.items():
            try:
                result[k] = float(v)
            except ValueError:
                result[k] = v

        result["hourly"] = hourly
        result["critical_service_pct"] = result.pop("critical_service_pct", 100.0)
        result["actions"] = chosen

        if messages_path.exists() and messages_path.stat().st_size > 0:
            result["agent_messages"] = pd.read_csv(messages_path)
        else:
            result["agent_messages"] = pd.DataFrame(columns=["Hour", "Sender", "Receiver", "Type", "Power_MW", "Detail"])

        return result


def profiles(settings, seed=None):
    """Compatibility helper. Profiles are generated by the C++ engine during simulation."""
    import numpy as np
    hours = np.arange(24)
    rng = np.random.default_rng(settings.seed if seed is None else seed)
    base = 150 + 25 * np.sin((hours - 7) * 2 * np.pi / 24) + 18 * np.exp(-((hours - 19) / 3.2) ** 2)
    solar_shape = np.maximum(0, np.sin((hours - 6) * np.pi / 12)); solar_shape /= solar_shape.max()
    wind_shape = .52 + .18 * np.sin((hours + 2) * 2 * np.pi / 24) + .08 * np.cos(hours * 4 * np.pi / 24)
    wind_shape = np.clip(wind_shape, .18, .9) / .9
    return (np.maximum(120, base * settings.demand_scale * rng.normal(1, .025, 24)),
            np.maximum(0, 145 * solar_shape * settings.solar_scale * rng.normal(1, .04, 24)),
            np.maximum(0, 55 * wind_shape * settings.wind_scale * rng.normal(1, .05, 24)))


def simulate(actions, settings, seed=None, line_capacity_overrides=None,
             substation_capacity_overrides=None, feeder_capacity_overrides=None, dispatch_mode=None):
    return _invoke(settings, seed, actions, "simulate", line_capacity_overrides,
                   substation_capacity_overrides, feeder_capacity_overrides, dispatch_mode)


def optimize(settings, seed=None, line_capacity_overrides=None,
             substation_capacity_overrides=None, feeder_capacity_overrides=None, dispatch_mode=None):
    result = _invoke(settings, seed, [0] * 24, "optimize", line_capacity_overrides,
                     substation_capacity_overrides, feeder_capacity_overrides, dispatch_mode)
    actions = result.pop("actions")
    return actions, result


def compare_modes(settings, seed=None, line_capacity_overrides=None,
                  substation_capacity_overrides=None, feeder_capacity_overrides=None):
    """Runs identical grid scenario under Centralized Baseline vs Decentralized ASI Swarm."""
    swarm = simulate([0] * 24, settings, seed, line_capacity_overrides,
                     substation_capacity_overrides, feeder_capacity_overrides, dispatch_mode="swarm")
    centralized = simulate([0] * 24, settings, seed, line_capacity_overrides,
                           substation_capacity_overrides, feeder_capacity_overrides, dispatch_mode="centralized")

    comparison = pd.DataFrame([
        {
            "Metric": "Critical Load Service (%)",
            "Decentralized Swarm (ASI)": f"{swarm.get('critical_service_pct', 100.0):.2f}%",
            "Centralized Baseline": f"{centralized.get('critical_service_pct', 100.0):.2f}%",
            "Delta (ASI Advantage)": f"{swarm.get('critical_service_pct', 100.0) - centralized.get('critical_service_pct', 100.0):+.2f}%"
        },
        {
            "Metric": "Unserved Energy (MWh)",
            "Decentralized Swarm (ASI)": f"{swarm.get('unserved', 0.0):.2f}",
            "Centralized Baseline": f"{centralized.get('unserved', 0.0):.2f}",
            "Delta (ASI Advantage)": f"{swarm.get('unserved', 0.0) - centralized.get('unserved', 0.0):+.2f}"
        },
        {
            "Metric": "Recovery Time (Hours)",
            "Decentralized Swarm (ASI)": f"{swarm.get('recovery_time_hours', 0.0):.1f} h",
            "Centralized Baseline": f"{centralized.get('recovery_time_hours', 0.0):.1f} h",
            "Delta (ASI Advantage)": f"{swarm.get('recovery_time_hours', 0.0) - centralized.get('recovery_time_hours', 0.0):+.1f} h"
        },
        {
            "Metric": "Cascading Containment",
            "Decentralized Swarm (ASI)": f"{swarm.get('cascading_containment_factor', 1.0)*100.0:.1f}%",
            "Centralized Baseline": f"{centralized.get('cascading_containment_factor', 1.0)*100.0:.1f}%",
            "Delta (ASI Advantage)": f"{(swarm.get('cascading_containment_factor', 1.0) - centralized.get('cascading_containment_factor', 1.0))*100.0:+.1f}%"
        },
        {
            "Metric": "Transmission Losses (MWh)",
            "Decentralized Swarm (ASI)": f"{swarm.get('transmission_losses', 0.0):.2f}",
            "Centralized Baseline": f"{centralized.get('transmission_losses', 0.0):.2f}",
            "Delta (ASI Advantage)": f"{swarm.get('transmission_losses', 0.0) - centralized.get('transmission_losses', 0.0):+.2f}"
        },
        {
            "Metric": "Total Operating Cost ($)",
            "Decentralized Swarm (ASI)": f"${swarm.get('cost', 0.0):,.0f}",
            "Centralized Baseline": f"${centralized.get('cost', 0.0):,.0f}",
            "Delta (ASI Advantage)": f"${swarm.get('cost', 0.0) - centralized.get('cost', 0.0):+,.0f}"
        }
    ])

    return {
        "swarm": swarm,
        "centralized": centralized,
        "comparison_table": comparison
    }
