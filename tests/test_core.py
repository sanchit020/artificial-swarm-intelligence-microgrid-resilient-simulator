import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.microgrid import Settings, simulate, optimize


def test_cpp_engine_returns_24_hours_and_50_consumers():
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026)
    assert len(result["hourly"]) == 24
    assert all(f"C{i:03d} delivered (MW)" in result["hourly"] for i in range(1, 51))
    assert all(f"C{i:03d} unserved (MW)" in result["hourly"] for i in range(1, 51))


def test_cpp_demand_conservation_and_flow_balance():
    result = simulate([0] * 24, Settings(seed=11, population=8, generations=1), seed=11)
    df = result["hourly"]
    assert abs(result["demand"] - result["delivered"] - result["unserved"]) < 1e-5
    delivered_cols = [f"C{i:03d} delivered (MW)" for i in range(1, 51)]
    demand_cols = [f"C{i:03d} demand (MW)" for i in range(1, 51)]
    assert (df[delivered_cols].sum(axis=1) - df["Delivered (MW)"]).abs().max() < 1e-5
    assert (df[demand_cols].sum(axis=1) - df["Demand (MW)"]).abs().max() < 1e-5
    assert (df["Unserved (MW)"] >= -1e-9).all()
    assert (df["Source flow balance residual (MW)"].abs() < 1e-5).all()
    assert (df["Consumer delivery balance residual (MW)"].abs() < 1e-5).all()


def test_cpp_mesh_corridors_carry_power():
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026)
    df = result["hourly"]
    cols = [c for c in df if c.startswith("Transmission ") and c.endswith(" flow (MW)")]
    assert sum(float(df[c].sum()) > 1e-7 for c in cols) > 0


def test_both_feeders_failed_isolate_consumer():
    from dashboard.network_flow import consumer_feeder_edges
    edges = [edge for edge in consumer_feeder_edges() if edge[1] == "C001"]
    assert len(edges) == 2
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026,
                      feeder_capacity_overrides={edge: 0.0 for edge in edges})
    assert result["hourly"]["C001 delivered (MW)"].sum() == 0
    assert result["unserved"] > 0


def test_substation_outage_is_applied():
    settings = Settings(seed=2026, population=8, generations=1)
    normal = simulate([0] * 24, settings, seed=2026)
    failed = simulate([0] * 24, settings, seed=2026, substation_capacity_overrides={"S6": 0.0})
    assert (failed["hourly"]["Source line Wind -> S6 flow (MW)"] == 0).all()
    assert failed["unserved"] >= 0
    assert failed["delivered"] <= normal["delivered"] + 1e-6


def test_cpp_optimizer_is_repeatable_and_returns_valid_actions():
    settings = Settings(seed=17, population=8, generations=1)
    a, r1 = optimize(settings, seed=17)
    b, r2 = optimize(settings, seed=17)
    assert a == b and len(a) == 24
    assert all(x in (-2, -1, 0, 1, 2) for x in a)
    assert abs(r1["cost"] - r2["cost"]) < 1e-8


def test_optimizer_is_not_worse_than_no_action_candidate():
    settings = Settings(seed=31, population=8, generations=1)
    actions, optimized = optimize(settings, seed=31)
    baseline = simulate([0] * 24, settings, seed=31)
    assert optimized["objective"] <= baseline["objective"] + 1e-7
