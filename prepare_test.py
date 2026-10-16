from pathlib import Path
from dashboard.microgrid import Settings, _write_config

root = Path.cwd()
settings = Settings(seed=2026, population=8, generations=3)

# Generate a valid baseline config using the same feeder topology as the dashboard.
_write_config(
    root / "baseline.cfg",
    settings, 2026, "simulate", [0] * 24,
    {}, {}, {}
)

print("Baseline config written.")
print("Feeder connections:", sum(
    line.startswith("feeder=")
    for line in (root / "baseline.cfg").read_text().splitlines()
))
