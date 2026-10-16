import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.microgrid import Settings, simulate
from dashboard.network_flow import consumer_feeder_edges


def test_source_line_failure_zeroes_that_edge_flow():
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026,
                      line_capacity_overrides={("Main Generator", "S3"): 0.0})
    assert (result["hourly"]["Source line Main Generator -> S3 flow (MW)"] == 0).all()


def test_corridor_failure_zeroes_both_directions():
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026,
                      line_capacity_overrides={("S3", "S5"): 0.0, ("S5", "S3"): 0.0})
    df = result["hourly"]
    assert (df["Transmission S3 -> S5 flow (MW)"] == 0).all()
    assert (df["Transmission S5 -> S3 flow (MW)"] == 0).all()


def test_combined_failures_apply_together():
    feeders = [e for e in consumer_feeder_edges() if e[1] == "C001"]
    result = simulate([0] * 24, Settings(seed=2026, population=8, generations=1), seed=2026,
                      line_capacity_overrides={("Solar", "S2"): 0.0, ("S3", "S5"): 0.0, ("S5", "S3"): 0.0},
                      substation_capacity_overrides={"S6": 0.0},
                      feeder_capacity_overrides={e: 0.0 for e in feeders})
    df = result["hourly"]
    assert (df["Source line Solar -> S2 flow (MW)"] == 0).all()
    assert (df["Transmission S3 -> S5 flow (MW)"] == 0).all()
    assert (df["Transmission S5 -> S3 flow (MW)"] == 0).all()
    assert (df["C001 delivered (MW)"] == 0).all()
    assert abs(result["demand"] - result["delivered"] - result["unserved"]) < 1e-5


def test_low_generation_produces_unserved_demand():
    s = Settings(seed=9, solar_scale=0.3, wind_scale=0.3, generator_capacity=60, population=8, generations=1)
    r = simulate([0] * 24, s, seed=9, substation_capacity_overrides={f"S{i}": 0.0 for i in range(1, 9)})
    assert r["delivered"] == 0
    assert abs(r["unserved"] - r["demand"]) < 1e-5


def test_multiple_failures_can_increase_unserved_energy():
    settings = Settings(seed=2026, population=8, generations=1)
    normal = simulate([0] * 24, settings, seed=2026)
    damaged = simulate(
        [0] * 24, settings, seed=2026,
        line_capacity_overrides={
            ("Solar", "S2"): 0.0,
            ("Main Generator", "S3"): 0.0,
            ("S2", "S8"): 0.0,
            ("S8", "S2"): 0.0,
            ("Battery", "S1"): 0.0,
        },
    )
    assert damaged["unserved"] > normal["unserved"]
    assert damaged["delivered"] < normal["delivered"]


def test_fixed_dispatch_outage_does_not_improve_unserved_energy():
    # Regression guard for the two-pass residual-network bug: with the same
    # dispatch and profile, removing network capacity must not create extra
    # deliverable power in this scenario.
    settings = Settings(seed=2026, population=8, generations=1)
    actions = [0] * 24
    normal = simulate(actions, settings, seed=2026)
    damaged = simulate(
        actions, settings, seed=2026,
        line_capacity_overrides={
            ("Solar", "S2"): 0.0,
            ("Main Generator", "S3"): 0.0,
            ("S2", "S8"): 0.0,
            ("S8", "S2"): 0.0,
            ("Battery", "S1"): 0.0,
        },
    )
    assert damaged["unserved"] >= normal["unserved"] - 1e-5
    assert damaged["delivered"] <= normal["delivered"] + 1e-5
