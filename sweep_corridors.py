from pathlib import Path
import re
import subprocess
import pandas as pd
from dashboard.microgrid import Settings, _write_config

root = Path.cwd()
exe = root / "build" / "Release" / "asi_engine.exe"
settings = Settings(seed=2026, population=8, generations=3)
actions = [0] * 24

def run_case(name, overrides):
    cfg = root / f"{name}.cfg"
    csv = root / f"{name}.csv"
    summary_path = root / f"{name}_summary.txt"

    _write_config(cfg, settings, 2026, "simulate", actions,
                  overrides, {}, {})

    p = subprocess.run(
        [str(exe), str(cfg), str(csv), str(summary_path)],
        cwd=str(root), capture_output=True, text=True
    )
    if p.returncode:
        raise RuntimeError(p.stderr + "\n" + p.stdout)

    df = pd.read_csv(csv)
    summary = {}
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        k, v = line.split("=", 1)
        if k != "actions":
            summary[k] = float(v)
    return df, summary

base, b = run_case("sweep_baseline", {})

# Discover unique physical corridors from the actual engine CSV.
edges = set()
for col in base.columns:
    m = re.fullmatch(r"Transmission (S\d+) -> (S\d+) flow \(MW\)", col)
    if m:
        u, v = m.groups()
        edges.add(tuple(sorted((u, v), key=lambda s: int(s[1:]))))

rows = []
for u, v in sorted(edges, key=lambda e: (int(e[0][1:]), int(e[1][1:]))):
    out, o = run_case(f"sweep_{u}_{v}", {(u, v): 0.0, (v, u): 0.0})

    uv = f"Transmission {u} -> {v} flow (MW)"
    vu = f"Transmission {v} -> {u} flow (MW)"
    flow_after = float(out[uv].sum() + out[vu].sum())

    rows.append({
        "Corridor": f"{u}-{v}",
        "BaselineFlow_MWh": round(float(base[uv].sum() + base[vu].sum()), 4),
        "OutageFlow_MWh": round(flow_after, 4),
        "DeltaUnserved_MWh": round(o["unserved"] - b["unserved"], 4),
        "DeltaDelivered_MWh": round(o["delivered"] - b["delivered"], 4),
        "DeltaCost": round(o["cost"] - b["cost"], 2),
        "CriticalService_pct": round(o["critical_service_pct"], 4),
    })

result = pd.DataFrame(rows)
result.to_csv(root / "corridor_outage_sweep.csv", index=False)
print(result.to_string(index=False))
print("\nSaved: corridor_outage_sweep.csv")
