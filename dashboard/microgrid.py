"""Python/Streamlit adapter for the compiled C++ ASI simulation engine.

All optimization, dispatch, battery accounting, and network-flow allocation execute in C++.
Python only serializes settings, supplies the visual topology's feeder mapping, and loads results.
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
    generator_capacity: float = 150.0
    battery_capacity: float = 120.0
    battery_power: float = 35.0
    initial_soc: float = 60.0
    reserve_soc: float = 18.0
    charge_efficiency: float = 0.94
    discharge_efficiency: float = 0.94
    generator_cost: float = 115.0
    battery_wear_cost: float = 8.0
    unserved_penalty: float = 18000.0
    reserve_penalty: float = 350.0
    generations: int = 3
    population: int = 8
    seed: int = 2026


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
    # Multi-config generators may put the executable under Release.
    found = list(BUILD.rglob("asi_engine.exe")) + list(BUILD.rglob("asi_engine"))
    if found:
        return found[0]
    raise RuntimeError("CMake completed but asi_engine executable was not found in build/.")


def _write_config(path, settings, seed, mode, actions, line_overrides, substation_overrides, feeder_overrides):
    pairs = {
        "mode": mode, "seed": int(settings.seed if seed is None else seed),
        "demand_scale": settings.demand_scale, "solar_scale": settings.solar_scale,
        "wind_scale": settings.wind_scale, "generator_capacity": settings.generator_capacity,
        "battery_capacity": settings.battery_capacity, "battery_power": settings.battery_power,
        "initial_soc": settings.initial_soc, "reserve_soc": settings.reserve_soc,
        "charge_efficiency": settings.charge_efficiency, "discharge_efficiency": settings.discharge_efficiency,
        "generator_cost": settings.generator_cost, "battery_wear_cost": settings.battery_wear_cost,
        "unserved_penalty": settings.unserved_penalty, "reserve_penalty": settings.reserve_penalty,
        "population": settings.population, "generations": settings.generations,
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
    # The Python topology module supplies the map's existing two-nearest-substation links.
    # No power allocation occurs in Python; these are static topology data passed to C++.
    for (u, v), cap in consumer_feeder_edges().items():
        lines.append(f"feeder={u},{v},{float(cap)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _invoke(settings, seed=None, actions=None, mode="simulate", line_capacity_overrides=None,
            substation_capacity_overrides=None, feeder_capacity_overrides=None):
    engine = _engine_path()
    with tempfile.TemporaryDirectory(prefix="asi_cpp_") as td:
        td = Path(td)
        cfg, hourly_path, summary_path = td / "config.txt", td / "hourly.csv", td / "summary.txt"
        _write_config(cfg, settings, seed, mode, actions, line_capacity_overrides,
                      substation_capacity_overrides, feeder_capacity_overrides)
        proc = subprocess.run([str(engine), str(cfg), str(hourly_path), str(summary_path)],
                              cwd=str(ROOT), capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"C++ ASI engine failed (exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}")
        hourly = pd.read_csv(hourly_path)
        summary = {}
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            k, v = line.split("=", 1)
            summary[k] = v
        chosen = [int(x) for x in summary.pop("actions").split(",")]
        result = {k: float(v) for k, v in summary.items()}
        result["hourly"] = hourly
        result["critical_service_pct"] = result.pop("critical_service_pct")
        result["actions"] = chosen
        return result


def profiles(settings, seed=None):
    """Compatibility helper. Profiles are generated by the C++ engine during simulation."""
    # Kept only for callers that used this helper; it is not part of the solver path.
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
             substation_capacity_overrides=None, feeder_capacity_overrides=None):
    return _invoke(settings, seed, actions, "simulate", line_capacity_overrides,
                   substation_capacity_overrides, feeder_capacity_overrides)


def optimize(settings, seed=None, line_capacity_overrides=None,
             substation_capacity_overrides=None, feeder_capacity_overrides=None):
    result = _invoke(settings, seed, [0] * 24, "optimize", line_capacity_overrides,
                     substation_capacity_overrides, feeder_capacity_overrides)
    actions = result.pop("actions")
    return actions, result
