from pathlib import Path
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
    summary_file = root / f"{name}_summary.txt"

    _write_config(cfg, settings, 2026, "simulate", actions,
                  overrides, {}, {})

    result = subprocess.run(
        [str(exe), str(cfg), str(csv), str(summary_file)],
        cwd=str(root), capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError(result.stderr + "\n" + result.stdout)

    df = pd.read_csv(csv)
    summary = {}
    for line in summary_file.read_text(encoding="utf-8").splitlines():
        k, v = line.split("=", 1)
        summary[k] = float(v) if k != "actions" else v
    return df, summary

base, b = run_case("corridor_baseline", {})
out, o = run_case(
    "corridor_outage",
    {("S3", "S5"): 0.0, ("S5", "S3"): 0.0}
)

print("=== S3-S5 PHYSICAL CORRIDOR OUTAGE ===")
for col in [
    "Transmission S3 -> S5 flow (MW)",
    "Transmission S5 -> S3 flow (MW)"
]:
    print(f"\n{col}")
    print(f"  Baseline total: {base[col].sum():.6f} MWh")
    print(f"  Outage total:   {out[col].sum():.6f} MWh")

print("\n=== SYSTEM COMPARISON ===")
for label, key in [
    ("Demand (MWh)", "demand"),
    ("Delivered (MWh)", "delivered"),
    ("Unserved (MWh)", "unserved"),
    ("Operating cost", "cost"),
    ("Critical service (%)", "critical_service_pct"),
]:
    print(f"{label:24s} baseline={b[key]:12.4f}  outage={o[key]:12.4f}")

print("\nChange in unserved energy:",
      round(o["unserved"] - b["unserved"], 6), "MWh")
