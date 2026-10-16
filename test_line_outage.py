from pathlib import Path
import subprocess
import pandas as pd
from dashboard.microgrid import Settings, _write_config

root = Path.cwd()
exe = root / "build" / "Release" / "asi_engine.exe"
settings = Settings(seed=2026, population=8, generations=3)
actions = [0] * 24

def run_case(name, line_overrides):
    cfg = root / f"{name}.cfg"
    hourly = root / f"{name}.csv"
    summary = root / f"{name}_summary.txt"

    _write_config(cfg, settings, 2026, "simulate", actions,
                  line_overrides, {}, {})

    proc = subprocess.run(
        [str(exe), str(cfg), str(hourly), str(summary)],
        cwd=str(root), capture_output=True, text=True
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr + "\n" + proc.stdout)

    frame = pd.read_csv(hourly)
    values = {}
    for line in summary.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        values[key] = value
    return frame, values

base, base_summary = run_case("line_test_baseline", {})

transmission_cols = [
    col for col in base.columns
    if col.startswith("Transmission ") and col.endswith(" flow (MW)")
]
if not transmission_cols:
    raise RuntimeError("No transmission-flow columns found.")

totals = {
    col: float(base[col].sum())
    for col in transmission_cols
}
active = [(col, total) for col, total in totals.items() if total > 1e-8]
if not active:
    raise RuntimeError("No transmission edge carries measurable flow.")

column, baseline_flow = max(active, key=lambda item: item[1])
edge = column[len("Transmission "):-len(" flow (MW)")]
source, target = edge.split(" -> ", 1)

print(f"Selected transmission edge: {source} -> {target}")
print(f"Baseline edge flow over 24 hours: {baseline_flow:.6f} MWh")

out, out_summary = run_case(
    "line_test_outage",
    {(source, target): 0.0}
)

outage_flow = float(out[column].sum())

print("\n=== BASELINE VS OUTAGE ===")
for label, key in [
    ("Total demand (MWh)", "demand"),
    ("Delivered energy (MWh)", "delivered"),
    ("Unserved energy (MWh)", "unserved"),
    ("Operating cost", "cost"),
    ("Critical service (%)", "critical_service_pct"),
]:
    print(f"{label:28s} baseline={float(base_summary[key]):12.4f}  "
          f"outage={float(out_summary[key]):12.4f}")

print(f"{'Selected edge flow (MWh)':28s} baseline={baseline_flow:12.4f}  "
      f"outage={outage_flow:12.4f}")

print("\nChange in unserved energy (MWh):",
      round(float(out_summary["unserved"]) - float(base_summary["unserved"]), 6))
