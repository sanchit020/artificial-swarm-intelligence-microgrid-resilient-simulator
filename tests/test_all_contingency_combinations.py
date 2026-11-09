import pytest
from dashboard.microgrid import Settings, optimize, simulate
from dashboard.network_flow import (
    SUBSTATIONS,
    TRANSMISSION_LINES,
    SOURCE_LINE_CAPACITY,
    consumer_feeder_edges,
)


@pytest.mark.parametrize(
    "name,settings_kwargs",
    [
        ("all_hydro_offline", {"hydro_capacity": 0.0}),
        ("all_solar_offline", {"solar_scale": 0.0}),
        ("all_wind_offline", {"wind_scale": 0.0}),
        ("all_battery_offline", {"battery_capacity": 0.0, "battery_power": 0.0}),
        ("all_generators_offline", {"generator_capacity": 0.0}),
        ("all_renewables_offline", {"solar_scale": 0.0, "wind_scale": 0.0, "hydro_capacity": 0.0}),
        ("all_renewables_and_battery_offline", {
            "solar_scale": 0.0, "wind_scale": 0.0, "hydro_capacity": 0.0,
            "battery_capacity": 0.0, "battery_power": 0.0,
        }),
        ("all_renewables_and_generators_offline", {
            "solar_scale": 0.0, "wind_scale": 0.0, "hydro_capacity": 0.0,
            "generator_capacity": 0.0,
        }),
        ("all_batteries_and_generators_offline", {
            "battery_capacity": 0.0, "battery_power": 0.0,
            "generator_capacity": 0.0,
        }),
        ("total_blackout_all_assets_zero", {
            "solar_scale": 0.0, "wind_scale": 0.0, "hydro_capacity": 0.0,
            "battery_capacity": 0.0, "battery_power": 0.0,
            "generator_capacity": 0.0,
        }),
        ("zero_demand", {"demand_scale": 0.0}),
        ("extreme_overload_demand", {"demand_scale": 2.5}),
        ("zero_substation_storage", {"substation_storage_capacity": 0.0, "substation_storage_power": 0.0}),
        ("zero_all_storage", {
            "substation_storage_capacity": 0.0, "substation_storage_power": 0.0,
            "battery_capacity": 0.0, "battery_power": 0.0,
        }),
    ],
)
def test_all_generation_and_storage_combinations(name, settings_kwargs):
    s = Settings(seed=2026, population=4, generations=1, **settings_kwargs)
    actions, opt_res = optimize(s, seed=2026)
    assert "delivered" in opt_res
    assert "cost" in opt_res
    sim_res = simulate(actions, s, seed=2026)
    assert "delivered" in sim_res
    assert "cost" in sim_res
    assert len(sim_res["hourly"]) == 24


@pytest.mark.parametrize("substation", SUBSTATIONS)
def test_individual_substation_outages(substation):
    s = Settings(seed=2026, population=4, generations=1)
    sub_overrides = {substation: 0.0}
    actions, opt_res = optimize(s, seed=2026, substation_capacity_overrides=sub_overrides)
    sim_res = simulate(actions, s, seed=2026, substation_capacity_overrides=sub_overrides)
    assert sim_res["delivered"] >= 0.0


def test_all_substations_offline_simultaneously():
    s = Settings(seed=2026, population=4, generations=1)
    sub_overrides = {sub: 0.0 for sub in SUBSTATIONS}
    actions, opt_res = optimize(s, seed=2026, substation_capacity_overrides=sub_overrides)
    sim_res = simulate(actions, s, seed=2026, substation_capacity_overrides=sub_overrides)
    assert sim_res["delivered"] == 0.0
    assert abs(sim_res["unserved"] - sim_res["demand"]) < 1e-5


def test_all_mesh_corridors_severed_simultaneously():
    s = Settings(seed=2026, population=4, generations=1)
    line_overrides = {}
    for u, v in TRANSMISSION_LINES:
        line_overrides[(u, v)] = 0.0
        line_overrides[(v, u)] = 0.0
    actions, opt_res = optimize(s, seed=2026, line_capacity_overrides=line_overrides)
    sim_res = simulate(actions, s, seed=2026, line_capacity_overrides=line_overrides)
    assert sim_res["delivered"] >= 0.0


def test_all_source_lines_severed_simultaneously():
    s = Settings(seed=2026, population=4, generations=1)
    line_overrides = {}
    for src, subs in SOURCE_LINE_CAPACITY.items():
        for sub, cap in subs.items():
            if cap > 0:
                line_overrides[(src, sub)] = 0.0
    actions, opt_res = optimize(s, seed=2026, line_capacity_overrides=line_overrides)
    sim_res = simulate(actions, s, seed=2026, line_capacity_overrides=line_overrides)
    assert sim_res["delivered"] >= 0.0


def test_complete_grid_total_isolation_all_lines_and_facilities_cut():
    s = Settings(
        seed=2026,
        population=4,
        generations=1,
        solar_scale=0.0,
        wind_scale=0.0,
        hydro_capacity=0.0,
        generator_capacity=0.0,
        battery_capacity=0.0,
        battery_power=0.0,
        substation_storage_capacity=0.0,
    )
    line_overrides = {}
    for u, v in TRANSMISSION_LINES:
        line_overrides[(u, v)] = 0.0
        line_overrides[(v, u)] = 0.0
    for src, subs in SOURCE_LINE_CAPACITY.items():
        for sub, cap in subs.items():
            if cap > 0:
                line_overrides[(src, sub)] = 0.0
    sub_overrides = {sub: 0.0 for sub in SUBSTATIONS}
    feeder_overrides = {e: 0.0 for e in consumer_feeder_edges()}

    actions, opt_res = optimize(
        s,
        seed=2026,
        line_capacity_overrides=line_overrides,
        substation_capacity_overrides=sub_overrides,
        feeder_capacity_overrides=feeder_overrides,
    )
    sim_res = simulate(
        actions,
        s,
        seed=2026,
        line_capacity_overrides=line_overrides,
        substation_capacity_overrides=sub_overrides,
        feeder_capacity_overrides=feeder_overrides,
    )
    assert sim_res["delivered"] == 0.0
    assert abs(sim_res["unserved"] - sim_res["demand"]) < 1e-5


@pytest.mark.parametrize("dispatch_mode", ["swarm", "centralized"])
def test_dispatch_modes_under_zero_battery(dispatch_mode):
    s = Settings(
        seed=2026,
        battery_capacity=0.0,
        battery_power=0.0,
        population=4,
        generations=1,
        dispatch_mode=dispatch_mode,
    )
    actions, opt_res = optimize(s, seed=2026, dispatch_mode=dispatch_mode)
    sim_res = simulate(actions, s, seed=2026, dispatch_mode=dispatch_mode)
    assert sim_res["delivered"] > 0.0


def test_dashboard_all_42_facilities_offline_simulation():
    # Simulate user selecting every single facility in the UI dropdown
    hydro_plants = 4
    solar_parks = 10
    wind_farms = 8
    battery_units = 8
    gen_units = 12

    eff_hydro_cap = 40.0 * max(0.0, 1.0 - (hydro_plants / 4.0))
    eff_solar_scale = 1.0 * max(0.0, 1.0 - (solar_parks / 10.0))
    eff_wind_scale = 1.0 * max(0.0, 1.0 - (wind_farms / 8.0))
    eff_bat_cap = 160.0 * max(0.0, 1.0 - (battery_units / 8.0))
    eff_bat_pwr = 50.0 * max(0.0, 1.0 - (battery_units / 8.0))
    eff_gen_cap = 175.0 * max(0.0, 1.0 - (gen_units / 12.0))

    s = Settings(
        demand_scale=1.0,
        solar_scale=float(eff_solar_scale),
        wind_scale=float(eff_wind_scale),
        hydro_scale=1.0,
        hydro_capacity=float(eff_hydro_cap),
        generator_capacity=float(eff_gen_cap),
        battery_capacity=float(eff_bat_cap),
        battery_power=float(eff_bat_pwr),
        population=4,
        generations=1,
        seed=2026,
    )
    actions, opt_res = optimize(s, seed=2026)
    assert opt_res["delivered"] >= 0.0
    sim_res = simulate(actions, s, seed=2026)
    assert sim_res["delivered"] >= 0.0
    assert abs(sim_res["delivered"] + sim_res["unserved"] - sim_res["demand"]) < 1e-5


def test_partial_facility_combinations_stress_sweep():
    # Sweep various partial outage percentages across asset classes
    fractions = [0.25, 0.50, 0.75, 1.0]
    for frac in fractions:
        s = Settings(
            solar_scale=1.0 * (1.0 - frac),
            wind_scale=1.0 * (1.0 - frac),
            hydro_capacity=40.0 * (1.0 - frac),
            generator_capacity=175.0 * (1.0 - frac),
            battery_capacity=160.0 * (1.0 - frac),
            battery_power=50.0 * (1.0 - frac),
            population=4,
            generations=1,
            seed=2026,
        )
        actions, opt_res = optimize(s, seed=2026)
        sim_res = simulate(actions, s, seed=2026)
        assert abs(sim_res["delivered"] + sim_res["unserved"] - sim_res["demand"]) < 1e-5

