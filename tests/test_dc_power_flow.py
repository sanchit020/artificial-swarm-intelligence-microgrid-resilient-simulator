import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.microgrid import Settings, simulate


def test_dc_power_flow_telemetry_in_hourly_dataframe():
    s = Settings(seed=2026, population=8, generations=1)
    res = simulate([0] * 24, s, seed=2026)
    df = res["hourly"]

    # Verify bus voltage angles and voltages for all 8 substations
    for i in range(1, 9):
        assert f"Bus S{i} angle (deg)" in df.columns
        assert f"Bus S{i} voltage (pu)" in df.columns
        assert (df[f"Bus S{i} voltage (pu)"] >= 0.85).all()
        assert (df[f"Bus S{i} voltage (pu)"] <= 1.05).all()

    # Verify physical losses and frequency deviation
    assert "Transmission losses (MW)" in df.columns
    assert (df["Transmission losses (MW)"] >= 0.0).all()
    assert "Frequency deviation (Hz)" in df.columns
    assert (df["Frequency deviation (Hz)"].abs() <= 1.5).all()


def test_islanding_detected_on_multiple_cuts():
    s = Settings(seed=2026, population=8, generations=1)
    # Isolate S7 by cutting S6-S7, S7-S1, S7-S8
    res = simulate([0] * 24, s, seed=2026, line_capacity_overrides={
        ("S6", "S7"): 0.0, ("S7", "S6"): 0.0,
        ("S7", "S1"): 0.0, ("S1", "S7"): 0.0,
        ("S7", "S8"): 0.0, ("S8", "S7"): 0.0,
    })
    assert res.get("island_count", 1) >= 2
    assert (res["hourly"]["Island count"] >= 2).any()

