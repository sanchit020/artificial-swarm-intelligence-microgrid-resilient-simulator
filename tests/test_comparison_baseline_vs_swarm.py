import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.microgrid import Settings, compare_modes


def test_compare_modes_executes_both_modes():
    s = Settings(seed=2026, population=8, generations=1)
    res = compare_modes(s, seed=2026, line_capacity_overrides={
        ("S3", "S5"): 0.0, ("S5", "S3"): 0.0,
        ("S2", "S8"): 0.0, ("S8", "S2"): 0.0
    })

    assert "swarm" in res
    assert "centralized" in res
    assert "comparison_table" in res

    table = res["comparison_table"]
    assert "Metric" in table.columns
    assert "Decentralized Swarm (ASI)" in table.columns
    assert "Centralized Baseline" in table.columns
    assert len(table) >= 5

