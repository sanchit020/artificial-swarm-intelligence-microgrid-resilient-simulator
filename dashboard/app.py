from pathlib import Path
import sys
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from dashboard.microgrid import Settings, optimize, simulate
from dashboard.topology import NODES, SUB_POS, _nearest_sub, _nearest_two_subs, build_topology
from dashboard.network_flow import SOURCE_LINE_CAPACITY, TRANSMISSION_LINES, consumer_feeder_edges

st.set_page_config(
    page_title="ASI Smart Power Grid SCADA",
    layout="wide"
)

# Professional SCADA Theme Styling
st.markdown("""<style>
.block-container {
    padding-top: 1.0rem !important;
    padding-bottom: 2.0rem !important;
    max-width: 1750px !important;
}

.hero {
    padding: 1.1rem 1.4rem;
    border-radius: 14px;
    background: linear-gradient(135deg, #0b1329 0%, #0f2744 50%, #17385c 100%);
    border: 1px solid rgba(56, 189, 248, 0.25);
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
    color: #fff;
    margin-bottom: 0.9rem;
}
.hero h1 {
    margin: 0;
    font-size: clamp(1.35rem, 2.2vw, 1.95rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(to right, #ffffff, #38bdf8, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero p {
    margin: 0.35rem 0 0;
    color: #94a3b8;
    font-size: 0.92rem;
    line-height: 1.4;
}

/* Custom Responsive KPI Grid (No text truncation) */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 0.9rem;
}
@media (max-width: 1200px) {
    .kpi-grid {
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }
}
.kpi-card {
    padding: 0.85rem 1.0rem;
    border: 1px solid rgba(56, 189, 248, 0.22);
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.90) 0%, rgba(11, 19, 41, 0.98) 100%);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    overflow: visible !important;
}
.kpi-label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94a3b8;
    margin-bottom: 0.3rem;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.25;
}
.kpi-val {
    font-size: clamp(1.15rem, 1.4vw, 1.5rem);
    font-weight: 800;
    color: #f8fafc;
    font-family: monospace;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.2;
}
.kpi-sub {
    font-size: 0.76rem;
    font-weight: 600;
    margin-top: 0.3rem;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    line-height: 1.2;
}

[data-testid="stSidebar"] {
    background-color: #0b1120 !important;
    border-right: 1px solid rgba(56, 189, 248, 0.12) !important;
}

/* Fix multiselect chip truncation in sidebar */
.stMultiSelect [data-baseweb="tag"] {
    max-width: 100% !important;
    white-space: normal !important;
    height: auto !important;
    padding-top: 2px !important;
    padding-bottom: 2px !important;
}
.stMultiSelect [data-baseweb="tag"] span {
    white-space: normal !important;
    word-break: break-word !important;
    font-size: 0.78rem !important;
}

.scada-panel {
    background: #0b1329;
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 12px;
    padding: 0.85rem 1.0rem;
    margin-bottom: 0.75rem;
}
.scada-badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 700;
    font-family: monospace;
}
</style>""", unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><h1>Centralized ASI Smart Power Grid</h1>'
    '<p>Contingency Simulation • Modified Edmonds–Karp Dynamic Rerouting • Solar, Wind & Hydro Dispatch • Substation & Battery Storage Reserves</p></div>',
    unsafe_allow_html=True,
)

# ==================== DATA STRUCTURES FOR LINES & FACILITIES ====================
# 1. Master options for transmission corridors
ALL_CORRIDORS_OPTION = "All 16 Inter-Substation Transmission Corridors"

CORRIDOR_LINE_MAP = {}
for u, v in TRANSMISSION_LINES:
    CORRIDOR_LINE_MAP[f"Corridor: {u} - {v}"] = (u, v)

# 2. Source-to-Substation Transmission Lines (Generators, Battery, Hydro, Solar, Wind)
SOURCE_TRANSMISSION_LINE_MAP = {
    # Main Generator transmission lines
    "Line: Main Generator -> S3": ("Main Generator", "S3"),
    "Line: Main Generator -> S4": ("Main Generator", "S4"),
    "Line: Main Generator -> S7": ("Main Generator", "S7"),
    # Battery transmission lines
    "Line: Central Battery -> S1": ("Battery", "S1"),
    "Line: Central Battery -> S4": ("Battery", "S4"),
    "Line: Central Battery -> S8": ("Battery", "S8"),
    # Hydro transmission lines
    "Line: Hydro -> S4": ("Hydro", "S4"),
    "Line: Hydro -> S5": ("Hydro", "S5"),
    # Solar transmission lines
    "Line: Solar -> S1": ("Solar", "S1"),
    "Line: Solar -> S2": ("Solar", "S2"),
    "Line: Solar -> S7": ("Solar", "S7"),
    "Line: Solar -> S8": ("Solar", "S8"),
    # Wind transmission lines
    "Line: Wind -> S2": ("Wind", "S2"),
    "Line: Wind -> S3": ("Wind", "S3"),
    "Line: Wind -> S5": ("Wind", "S5"),
    "Line: Wind -> S6": ("Wind", "S6"),
}

# 3. Individual Plant Conduit Lines
PLANT_CONDUIT_LINE_MAP = {}
for n, (x, y, kind) in NODES.items():
    if kind in ("solar", "wind", "hydro", "battery", "generator"):
        subs = _nearest_two_subs(x, y)
        for s in subs:
            PLANT_CONDUIT_LINE_MAP[f"Conduit: {n} -> {s}"] = (n, s)

# Full line selection options
LINE_SELECTION_OPTIONS = (
    [ALL_CORRIDORS_OPTION]
    + list(CORRIDOR_LINE_MAP.keys())
    + list(SOURCE_TRANSMISSION_LINE_MAP.keys())
    + list(PLANT_CONDUIT_LINE_MAP.keys())
)

# 4. Facilities Map (Separate selection for complete physical plants/facilities)
FACILITY_NAME_MAP = {
    # Hydro Plants
    "Hydro Plant 04 (Near S5 & S6)": "Hydro 04",
    "Hydro Plant 01 (Near S4 & S3)": "Hydro 01",
    "Hydro Plant 02 (Near S4 & S5)": "Hydro 02",
    "Hydro Plant 03 (Near S5 & S4)": "Hydro 03",
}
# Solar Parks
for i in range(1, 11):
    tag = f"Solar {i:02d}"
    subs = _nearest_two_subs(*NODES[tag][:2])
    FACILITY_NAME_MAP[f"Solar Park {i:02d} (Near {subs[0]} & {subs[1]})"] = tag

# Wind Farms
for i in range(1, 9):
    tag = f"Wind {i:02d}"
    subs = _nearest_two_subs(*NODES[tag][:2])
    FACILITY_NAME_MAP[f"Wind Farm {i:02d} (Near {subs[0]} & {subs[1]})"] = tag

# Battery Storage Units
for i in range(1, 9):
    tag = f"Battery {i:02d}"
    subs = _nearest_two_subs(*NODES[tag][:2])
    FACILITY_NAME_MAP[f"Battery Storage Unit {i:02d} (Near {subs[0]} & {subs[1]})"] = tag

# Thermal Generator Units
for i in range(1, 13):
    tag = f"Gen {i:02d}"
    subs = _nearest_two_subs(*NODES[tag][:2])
    FACILITY_NAME_MAP[f"Thermal Generator Unit {i:02d} (Near {subs[0]} & {subs[1]})"] = tag

# Substation Hub Facilities
for i in range(1, 9):
    FACILITY_NAME_MAP[f"Substation Facility S{i}"] = f"S{i}"

FACILITY_SELECTION_OPTIONS = list(FACILITY_NAME_MAP.keys())

# Sidebar Controls
with st.sidebar:
    st.header("Grid Controls & Scenario")

    with st.expander("Renewable Generation Controls", expanded=True):
        solar_scale = st.slider(
            "Solar Generation Scale",
            min_value=0.0,
            max_value=1.8,
            value=1.0,
            step=0.05,
            key="solar_scale",
            help="Multiplies diurnal solar irradiance curve."
        )
        wind_scale = st.slider(
            "Wind Generation Scale",
            min_value=0.0,
            max_value=1.8,
            value=1.0,
            step=0.05,
            key="wind_scale",
            help="Multiplies wind turbine generation curve."
        )
        # Single intuitive slider for Hydro Generation
        hydro_generation_mw = st.slider(
            "Hydro Generation Output (MW)",
            min_value=0.0,
            max_value=100.0,
            value=40.0,
            step=5.0,
            key="hydro_generation_mw",
            help="Total hydroelectric power capacity injected into river substations S4 and S5."
        )

    with st.expander("Grid Demand & Generator", expanded=True):
        demand_scale = st.slider(
            "Consumer Demand Scale",
            min_value=0.70,
            max_value=1.40,
            value=1.0,
            step=0.05,
            key="demand_scale"
        )
        generator_capacity = st.slider(
            "Main Generator Capacity (MW)",
            min_value=60.0,
            max_value=240.0,
            value=175.0,
            step=5.0,
            key="gen_cap"
        )

    with st.expander("Battery & Substation Storage", expanded=True):
        battery_capacity = st.slider(
            "Central Battery Capacity (MWh)",
            min_value=60.0,
            max_value=300.0,
            value=160.0,
            step=10.0,
            key="bat_cap"
        )
        battery_power = st.slider(
            "Central Battery Power Limit (MW)",
            min_value=20.0,
            max_value=80.0,
            value=50.0,
            step=5.0,
            key="bat_pwr"
        )
        sub_storage_cap = st.slider(
            "Substation Storage Capacity (MWh/sub)",
            min_value=5.0,
            max_value=30.0,
            value=15.0,
            step=1.0,
            key="sub_cap",
            help="15 MWh per substation = 120 MWh total reserve across 8 substations"
        )
        sub_storage_pwr = st.slider(
            "Substation Storage Discharge Limit (MW)",
            min_value=2.0,
            max_value=12.0,
            value=6.0,
            step=1.0,
            key="sub_pwr"
        )

    # 1. TRANSMISSION LINES SELECTION (purely transmission and connecting lines)
    with st.expander("Transmission & Connecting Line Failures", expanded=True):
        selected_lines = st.multiselect(
            "Select Transmission & Connecting Lines to Sever",
            options=LINE_SELECTION_OPTIONS,
            default=[],
            key="line_selection",
            help="Select any transmission line, generator line, battery line, or conduit to sever it. The connecting facility remains online."
        )

    # 2. SEPARATE DROPDOWN FOR ENTIRE FACILITY OUTAGES
    with st.expander("Entire Facility & Plant Outages", expanded=True):
        selected_facilities = st.multiselect(
            "Select Entire Facility / Plant to Take Down",
            options=FACILITY_SELECTION_OPTIONS,
            default=[],
            key="facility_selection",
            help="Select any physical plant or facility (e.g. Hydro Plant 04). The entire facility and all its connecting power lines will go down simultaneously."
        )

        total_contingencies = len(selected_lines) + len(selected_facilities)
        if total_contingencies > 0:
            st.warning(f"Active Contingency: {len(selected_lines)} line(s) and {len(selected_facilities)} facility(s) offline.")
        else:
            st.success("All transmission lines and physical facilities operational.")

    with st.expander("Genetic Algorithm Optimizer", expanded=False):
        population = st.slider("Population Size", min_value=8, max_value=32, value=8, step=4, key="ga_pop")
        generations = st.slider("Generations", min_value=1, max_value=10, value=3, step=1, key="ga_gen")
        seed = st.number_input("Reproducible Random Seed", min_value=0, max_value=999999, value=2026, step=1, key="ga_seed")

    st.divider()
    run_simulation = st.button("Execute Simulation & Dynamic Reroute", type="primary", use_container_width=True)

# ==================== PROCESS DISRUPTIONS & FAULTS ====================
line_overrides = {}
substation_overrides = {}
feeder_overrides = {}
failed_visual_edges = set()
failed_facility_nodes = set()
severed_lines_display = []

# Process Dropdown 2: Entire Facility Outages
for fac_lbl in selected_facilities:
    node_tag = FACILITY_NAME_MAP[fac_lbl]
    failed_facility_nodes.add(node_tag)

    if node_tag.startswith("S") and len(node_tag) == 2:
        substation_overrides[node_tag] = 0.0
    else:
        # Take down all connecting conduit lines for this facility
        x, y, kind = NODES[node_tag]
        source_class = {"solar": "Solar", "wind": "Wind", "hydro": "Hydro", "battery": "Battery", "generator": "Main Generator"}[kind]
        for sub in _nearest_two_subs(x, y):
            failed_visual_edges.add((node_tag, sub))
            severed_lines_display.append(f"Conduit: {node_tag} -> {sub} (Facility Tripped)")

# Calculate proportional capacity reductions from facility outages
failed_hydro_plants = [f for f in failed_facility_nodes if f.startswith("Hydro")]
failed_solar_parks = [f for f in failed_facility_nodes if f.startswith("Solar")]
failed_wind_farms = [f for f in failed_facility_nodes if f.startswith("Wind")]
failed_battery_units = [f for f in failed_facility_nodes if f.startswith("Battery")]
failed_gen_units = [f for f in failed_facility_nodes if f.startswith("Gen")]

eff_hydro_cap = hydro_generation_mw * max(0.0, 1.0 - (len(failed_hydro_plants) / 4.0))
eff_solar_scale = solar_scale * max(0.0, 1.0 - (len(failed_solar_parks) / 10.0))
eff_wind_scale = wind_scale * max(0.0, 1.0 - (len(failed_wind_farms) / 8.0))
eff_bat_cap = battery_capacity * max(0.0, 1.0 - (len(failed_battery_units) / 8.0))
eff_bat_pwr = battery_power * max(0.0, 1.0 - (len(failed_battery_units) / 8.0))
eff_gen_cap = generator_capacity * max(0.0, 1.0 - (len(failed_gen_units) / 12.0))

# Process Dropdown 1: Transmission & Connecting Lines
failed_all_mesh = ALL_CORRIDORS_OPTION in selected_lines

if failed_all_mesh:
    for u, v in TRANSMISSION_LINES:
        line_overrides[(u, v)] = 0.0
        line_overrides[(v, u)] = 0.0
        failed_visual_edges.add((u, v))
        failed_visual_edges.add((v, u))
        severed_lines_display.append(f"Corridor: {u} - {v}")
else:
    for item in selected_lines:
        if item in CORRIDOR_LINE_MAP:
            u, v = CORRIDOR_LINE_MAP[item]
            line_overrides[(u, v)] = 0.0
            line_overrides[(v, u)] = 0.0
            failed_visual_edges.add((u, v))
            failed_visual_edges.add((v, u))
            severed_lines_display.append(f"Corridor: {u} - {v}")
        elif item in SOURCE_TRANSMISSION_LINE_MAP:
            src, sub = SOURCE_TRANSMISSION_LINE_MAP[item]
            line_overrides[(src, sub)] = 0.0
            failed_visual_edges.add((src, sub))
            severed_lines_display.append(f"Line: {src} -> {sub}")
        elif item in PLANT_CONDUIT_LINE_MAP:
            plant, sub = PLANT_CONDUIT_LINE_MAP[item]
            failed_visual_edges.add((plant, sub))
            severed_lines_display.append(f"Conduit: {plant} -> {sub}")

            # Deduct conduit capacity share from source line
            x, y, kind = NODES[plant]
            source_class = {"solar": "Solar", "wind": "Wind", "hydro": "Hydro", "battery": "Battery", "generator": "Main Generator"}[kind]
            nom_cap = float(SOURCE_LINE_CAPACITY.get(source_class, {}).get(sub, 0.0))
            if nom_cap > 0:
                total_conduits = sum(1 for p, (px, py, pk) in NODES.items() if pk == kind and sub in _nearest_two_subs(px, py))
                total_conduits = max(1, total_conduits)
                conduit_share = nom_cap / total_conduits
                current_cap = line_overrides.get((source_class, sub), nom_cap)
                line_overrides[(source_class, sub)] = max(0.0, current_cap - conduit_share)

sim_settings = Settings(
    demand_scale=float(demand_scale),
    solar_scale=float(eff_solar_scale),
    wind_scale=float(eff_wind_scale),
    hydro_scale=1.0,
    hydro_capacity=float(eff_hydro_cap),
    generator_capacity=float(eff_gen_cap),
    battery_capacity=float(eff_bat_cap),
    battery_power=float(eff_bat_pwr),
    substation_storage_capacity=float(sub_storage_cap),
    substation_storage_power=float(sub_storage_pwr),
    population=int(population),
    generations=int(generations),
    seed=int(seed),
    dispatch_mode="swarm",
)

# Run simulation
should_run = run_simulation or "asi_sim_result" not in st.session_state
if should_run:
    with st.spinner("Executing Centralized ASI dispatch, Edmonds–Karp dynamic rerouting & DC power flow..."):
        t0 = time.perf_counter()
        actions, result = optimize(
            sim_settings,
            seed=int(seed),
            line_capacity_overrides=line_overrides,
            substation_capacity_overrides=substation_overrides,
            feeder_capacity_overrides=feeder_overrides,
            dispatch_mode="swarm"
        )
        # Healthy baseline with identical optimization for fair physical comparison
        healthy_settings = Settings(
            demand_scale=float(demand_scale),
            solar_scale=float(solar_scale),
            wind_scale=float(wind_scale),
            hydro_scale=1.0,
            hydro_capacity=float(hydro_generation_mw),
            generator_capacity=float(generator_capacity),
            battery_capacity=float(battery_capacity),
            battery_power=float(battery_power),
            substation_storage_capacity=float(sub_storage_cap),
            substation_storage_power=float(sub_storage_pwr),
            population=int(population),
            generations=int(generations),
            seed=int(seed),
            dispatch_mode="swarm"
        )
        _, normal_baseline = optimize(healthy_settings, seed=int(seed), dispatch_mode="swarm")

        st.session_state["asi_sim_result"] = result
        st.session_state["baseline_sim_result"] = normal_baseline
        st.session_state["actions"] = actions
        st.session_state["failed_visual_edges"] = failed_visual_edges
        st.session_state["failed_facility_nodes"] = failed_facility_nodes
        st.session_state["selected_lines"] = list(selected_lines)
        st.session_state["selected_facilities"] = list(selected_facilities)
        st.session_state["severed_lines_display"] = list(severed_lines_display)
        st.session_state["substation_overrides"] = dict(substation_overrides)
        st.session_state["sim_elapsed"] = time.perf_counter() - t0

res = st.session_state["asi_sim_result"]
base_res = st.session_state["baseline_sim_result"]
df = res["hourly"]
active_lines = st.session_state.get("selected_lines", [])
active_facilities = st.session_state.get("selected_facilities", [])
failed_edges_set = st.session_state.get("failed_visual_edges", set())
failed_fac_nodes = st.session_state.get("failed_facility_nodes", set())
active_severed_lines = st.session_state.get("severed_lines_display", [])

# Top KPI Strip (Custom non-truncating HTML cards)
delivery_ratio = (res.get('delivered', 0.0) / max(res.get('demand', 1.0), 1e-9)) * 100.0
crit_ratio = res.get('critical_service_pct', 100.0)
rec_time = res.get('recovery_time_hours', 0.0)
total_cuts_count = len(active_lines) + len(active_facilities)
outage_text = f"{total_cuts_count} Offline" if total_cuts_count else "0 Offline"
outage_sub = "Contingencies Managed" if total_cuts_count else "All Systems Normal"
outage_color = "#f87171" if total_cuts_count else "#34d399"

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">TOTAL OPERATING COST</div>
        <div class="kpi-val">${res.get('cost', 0.0):,.0f}</div>
        <div class="kpi-sub" style="color:#94a3b8;">24-Hour OPEX</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">DELIVERED ENERGY</div>
        <div class="kpi-val">{res.get('delivered', 0.0):,.1f} MWh</div>
        <div class="kpi-sub" style="color:#34d399;">{delivery_ratio:.1f}% Demand Met</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">CRITICAL FACILITY SERVICE</div>
        <div class="kpi-val">{crit_ratio:.1f}%</div>
        <div class="kpi-sub" style="color:#34d399;">7 of 7 Hospitals Online</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">CONTINGENCY RECOVERY TIME</div>
        <div class="kpi-val">{rec_time:.1f} h</div>
        <div class="kpi-sub" style="color:#38bdf8;">Dynamic Reroute Time</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">ACTIVE CONTINGENCIES</div>
        <div class="kpi-val" style="color:{outage_color};">{outage_text}</div>
        <div class="kpi-sub" style="color:{outage_color};">{outage_sub}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Contingency status banner (No emojis)
if total_cuts_count > 0:
    delta_delivered = float(res.get("delivered", 0.0)) - float(base_res.get("delivered", 0.0))
    summary_parts = []
    if active_lines:
        summary_parts.append(f"Lines Severed: {', '.join(active_lines)}")
    if active_facilities:
        summary_parts.append(f"Facilities Offline: {', '.join(active_facilities)}")
    contingency_summary_str = " | ".join(summary_parts)

    loss_tag = f"<span style='color:#f87171;font-weight:700;'>{delta_delivered:+,.1f} MWh</span>" if delta_delivered < -0.01 else f"<span style='color:#34d399;font-weight:700;'>{delta_delivered:+,.1f} MWh</span>"
    st.markdown(
        f"""<div style="background:rgba(239,68,68,0.10);border:1px solid rgba(239,68,68,0.40);border-radius:10px;padding:0.6rem 1.0rem;margin:0.4rem 0 0.8rem;">
        <span style="color:#f87171;font-weight:700;">[CONTINGENCY ACTIVE] Injected Faults:</span> <span style="color:#fca5a5;">{contingency_summary_str}</span>
        &nbsp;|&nbsp; <b>Delivered vs Healthy Baseline:</b> {loss_tag}
        &nbsp;|&nbsp; <b>Centralized ASI Status:</b> Dynamic Edmonds–Karp rerouting active, discharging substation and BESS reserves.
        </div>""",
        unsafe_allow_html=True
    )
else:
    st.markdown(
        """<div style="background:rgba(16,185,129,0.10);border:1px solid rgba(16,185,129,0.35);border-radius:10px;padding:0.6rem 1.0rem;margin:0.4rem 0 0.8rem;">
        <span style="color:#34d399;font-weight:700;">[NORMAL STATUS] Grid Healthy:</span> All transmission lines, generators, batteries, and power plants operational.
        </div>""",
        unsafe_allow_html=True
    )

# Dynamic Map Controls Bar
mc1, mc2, mc3, mc4 = st.columns([2.2, 1.1, 0.9, 0.8])
with mc1:
    # Default to 12 (Noon - Peak Solar) so Solar is prominently active and visible
    selected_hour = st.slider(
        "Simulation Hour (0 to 23)",
        min_value=0,
        max_value=23,
        value=12,
        step=1,
        key="map_hour",
        help="Scrub hour from 0 to 23. Solar is active during daylight (06:00 to 18:00) with peak at 12:00."
    )
with mc2:
    map_size = st.selectbox("Map Size Toggle", ["Standard (720px)", "Compact (560px)", "Expanded (880px)"], index=0)
with mc3:
    map_view = st.selectbox("Map View Focus", ["Core Mesh (Zoomed)", "Full Territory", "North Sector", "South Sector"], index=0)
with mc4:
    show_feeders = st.checkbox("Show Feeders", value=True)

size_code = "expanded" if "Expanded" in map_size else ("compact" if "Compact" in map_size else "standard")
focus_code = "mesh" if "Core Mesh" in map_view else ("full" if "Full Territory" in map_view else ("north" if "North Sector" in map_view else "south"))

selected_row = df.iloc[selected_hour]
base_row = base_res["hourly"].iloc[selected_hour] if base_res is not None and "hourly" in base_res else None

# Prepare hourly map dictionary
map_hour_data = selected_row.to_dict()
map_hour_data["delivered"] = {f"D{i}": float(selected_row.get(f"D{i} delivered (MW)", 0.0)) for i in range(1, 9)}
map_hour_data["demand"] = {f"D{i}": float(selected_row.get(f"D{i} demand (MW)", 0.0)) for i in range(1, 9)}

# ==================== DYNAMIC MAP (FULL CONTAINER WIDTH) ====================
st.plotly_chart(
    build_topology(
        map_hour_data,
        failed_edges=failed_edges_set,
        failed_substations=set(st.session_state.get("substation_overrides", {})),
        failed_facilities=failed_fac_nodes,
        view_focus=focus_code,
        show_feeders=show_feeders,
        show_assets=True,
        map_size=size_code
    ),
    use_container_width=True,
    config={"displayModeBar": True, "scrollZoom": True, "displaylogo": False}
)

# ==================== HORIZONTAL TELEMETRY STRIP (BELOW MAP) ====================
hour_del = float(selected_row.get("Delivered (MW)", 0.0))
hour_dem = float(selected_row.get("Demand (MW)", 0.0))
hour_uns = float(selected_row.get("Unserved (MW)", 0.0))
hour_pct = (hour_del / max(hour_dem, 1e-9)) * 100.0

is_daylight = (6 <= selected_hour <= 18)
daylight_tag = "Daylight Peak (12:00)" if (10 <= selected_hour <= 14) else ("Daylight Hours" if is_daylight else "Night Hours (Zero Solar)")

solar_val = float(selected_row.get('Solar (MW)', 0.0))
wind_val = float(selected_row.get('Wind (MW)', 0.0))
hydro_val = float(selected_row.get('Hydro (MW)', 0.0))
hydro_used = float(selected_row.get('Hydro used (MW)', 0.0))
gen_val = float(selected_row.get('Generator used (MW)', 0.0))
bat_dis = float(selected_row.get('Battery discharge (MW)', 0.0))
sub_dis = float(selected_row.get('Substation storage discharge (MW)', 0.0))
bat_soc = float(selected_row.get('Battery SOC (MWh)', 0.0))
sub_soc = float(selected_row.get('Substation storage SOC (MWh)', 0.0))

t1, t2, t3, t4 = st.columns(4)

with t1:
    st.markdown(f"""
    <div class="scada-panel">
        <div style="font-size:0.75rem;font-weight:700;color:#38bdf8;text-transform:uppercase;">
            Hour {selected_hour:02d}:00 Status &nbsp;<span style="color:#94a3b8;font-weight:500;">({daylight_tag})</span>
        </div>
        <div style="font-size:1.35rem;font-weight:800;color:#fff;font-family:monospace;margin:0.25rem 0 0.4rem;">
            {hour_del:.1f} <span style="font-size:0.85rem;color:#94a3b8;">/ {hour_dem:.1f} MW</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <span class="scada-badge" style="background:rgba(16,185,129,0.2);color:#34d399;border:1px solid #10b981;">{hour_pct:.1f}% SERVED</span>
            <span class="scada-badge" style="background:rgba(239,68,68,0.2);color:#f87171;border:1px solid #ef4444;">{hour_uns:.2f} MW UNSERVED</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with t2:
    st.markdown(f"""
    <div class="scada-panel">
        <div style="font-size:0.75rem;font-weight:700;color:#f59e0b;text-transform:uppercase;">Renewable Generation Mix</div>
        <div style="font-size:0.86rem;color:#cbd5e1;line-height:1.6;margin-top:0.2rem;">
            <b>Solar PV:</b> <span style="color:#f59e0b;font-weight:700;">{solar_val:.1f} MW</span> {'(Active Daylight)' if is_daylight else '(Night - Zero Sun)'}<br>
            <b>Wind Farm:</b> <span style="color:#14b8a6;font-weight:700;">{wind_val:.1f} MW</span><br>
            <b>Hydro Power:</b> <span style="color:#06b6d4;font-weight:700;">{hydro_val:.1f} MW</span> (Used: {hydro_used:.1f} MW)<br>
            <b>Main Generator:</b> <span style="color:#f97316;font-weight:700;">{gen_val:.1f} MW</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with t3:
    st.markdown(f"""
    <div class="scada-panel">
        <div style="font-size:0.75rem;font-weight:700;color:#a855f7;text-transform:uppercase;">Storage & Reserves</div>
        <div style="font-size:0.86rem;color:#cbd5e1;line-height:1.6;margin-top:0.2rem;">
            <b>Battery Discharge:</b> <span style="color:#a855f7;font-weight:700;">{bat_dis:.1f} MW</span><br>
            <b>Substation Discharge:</b> <span style="color:#10b981;font-weight:700;">{sub_dis:.1f} MW</span><br>
            <b>Central BESS SOC:</b> <span style="color:#f8fafc;font-weight:700;">{bat_soc:.1f} MWh</span><br>
            <b>Substation Reserve:</b> <span style="color:#f8fafc;font-weight:700;">{sub_soc:.1f} MWh</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with t4:
    crit_count = 0
    crit_badges = []
    for ci in (3, 10, 17, 24, 31, 38, 45):
        c_tag = f"C{ci:03d}"
        c_del = float(selected_row.get(f"{c_tag} delivered (MW)", 0.0))
        c_dem = float(selected_row.get(f"{c_tag} demand (MW)", 0.0))
        ok = c_del >= c_dem * 0.99
        if ok:
            crit_count += 1
        crit_badges.append(f"<span style='color:{'#34d399' if ok else '#f87171'};font-weight:700;'>{c_tag}</span>")

    st.markdown(f"""
    <div class="scada-panel">
        <div style="font-size:0.75rem;font-weight:700;color:#f43f5e;text-transform:uppercase;">Critical Facilities (7)</div>
        <div style="font-size:1.1rem;font-weight:800;color:#34d399;font-family:monospace;margin:0.2rem 0;">
            {crit_count} / 7 Online
        </div>
        <div style="font-size:0.82rem;color:#94a3b8;line-height:1.5;">
            Protected Emergency Nodes:<br>
            {' • '.join(crit_badges)}
        </div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ==================== FAILURE & DYNAMIC REROUTING TABLE ====================
st.subheader("Failure Simulation & Dynamic Rerouting Analysis")

if total_cuts_count > 0:
    failed_rows = []
    rerouted_corridors = []

    # 1. Severed transmission corridors
    for u, v in TRANSMISSION_LINES:
        is_cut = (u, v) in failed_edges_set or (v, u) in failed_edges_set
        f_base_uv = float(base_row.get(f"Transmission {u} -> {v} flow (MW)", 0.0)) if base_row is not None else 0.0
        f_base_vu = float(base_row.get(f"Transmission {v} -> {u} flow (MW)", 0.0)) if base_row is not None else 0.0
        f_base = max(f_base_uv, f_base_vu)

        f_curr_uv = float(selected_row.get(f"Transmission {u} -> {v} flow (MW)", 0.0))
        f_curr_vu = float(selected_row.get(f"Transmission {v} -> {u} flow (MW)", 0.0))
        f_curr = max(f_curr_uv, f_curr_vu)

        if is_cut:
            failed_rows.append({
                "Severed Component / Line": f"Corridor {u} - {v}",
                "Status": "SEVERED / TRIPPED",
                "Pre-Failure Flow (MW)": round(f_base, 2),
                "Post-Failure Flow (MW)": 0.0,
                "Displaced Deficit (MW)": round(f_base, 2),
                "Rating (MW)": 48.0
            })
        else:
            diff = f_curr - f_base
            if abs(diff) > 0.1 or f_curr > 0.1:
                direction = f"{u} → {v}" if f_curr_uv >= f_curr_vu else f"{v} → {u}"
                rerouted_corridors.append({
                    "Surviving Corridor": f"{u} - {v}",
                    "Active Direction": direction,
                    "Nominal Baseline Flow (MW)": round(f_base, 2),
                    "Post-Failure Rerouted Flow (MW)": round(f_curr, 2),
                    "Diverted Load Absorbed (MW)": round(diff, 2),
                    "Thermal Loading (%)": f"{(f_curr / 48.0) * 100.0:.1f}%"
                })

    # 2. Severed source and plant lines
    for item in active_lines:
        if item in SOURCE_TRANSMISSION_LINE_MAP:
            src, sub = SOURCE_TRANSMISSION_LINE_MAP[item]
            f_base_src = float(base_row.get(f"Source line {src} -> {sub} flow (MW)", 0.0)) if base_row is not None else 0.0
            failed_rows.append({
                "Severed Component / Line": f"Line: {src} -> {sub}",
                "Status": "SEVERED / TRIPPED",
                "Pre-Failure Flow (MW)": round(f_base_src, 2),
                "Post-Failure Flow (MW)": 0.0,
                "Displaced Deficit (MW)": round(f_base_src, 2),
                "Rating (MW)": float(SOURCE_LINE_CAPACITY.get(src, {}).get(sub, 0.0))
            })
        elif item in PLANT_CONDUIT_LINE_MAP:
            plant, sub = PLANT_CONDUIT_LINE_MAP[item]
            x, y, kind = NODES[plant]
            source_class = {"solar": "Solar", "wind": "Wind", "hydro": "Hydro", "battery": "Battery", "generator": "Main Generator"}[kind]
            nom_cap = float(SOURCE_LINE_CAPACITY.get(source_class, {}).get(sub, 0.0))
            total_conduits = sum(1 for p, (px, py, pk) in NODES.items() if pk == kind and sub in _nearest_two_subs(px, py))
            total_conduits = max(1, total_conduits)
            conduit_rating = nom_cap / total_conduits if nom_cap > 0 else 10.0
            f_base_src = float(base_row.get(f"Source line {source_class} -> {sub} flow (MW)", 0.0)) if base_row is not None else 0.0
            conduit_flow = f_base_src / total_conduits if nom_cap > 0 else 0.0

            failed_rows.append({
                "Severed Component / Line": f"Conduit: {plant} -> {sub}",
                "Status": "CONDUIT SEVERED",
                "Pre-Failure Flow (MW)": round(conduit_flow, 2),
                "Post-Failure Flow (MW)": 0.0,
                "Displaced Deficit (MW)": round(conduit_flow, 2),
                "Rating (MW)": round(conduit_rating, 1)
            })

    # 3. Offline facilities
    for fac_lbl in active_facilities:
        node_tag = FACILITY_NAME_MAP[fac_lbl]
        unit_rating = "-"
        if node_tag.startswith("Hydro"):
            unit_rating = f"{hydro_generation_mw / 4.0:.1f} MW"
        elif node_tag.startswith("Gen"):
            unit_rating = f"{generator_capacity / 12.0:.1f} MW"
        elif node_tag.startswith("Battery"):
            unit_rating = f"{battery_power / 8.0:.1f} MW"
        elif node_tag.startswith("Solar"):
            unit_rating = "10.0% Solar PV"
        elif node_tag.startswith("Wind"):
            unit_rating = "12.5% Wind Farm"
        elif node_tag.startswith("S") and len(node_tag) == 2:
            unit_rating = "82.0 MW"

        failed_rows.append({
            "Severed Component / Line": fac_lbl,
            "Status": "PLANT DOWN (Conduits Cut)",
            "Pre-Failure Flow (MW)": unit_rating,
            "Post-Failure Flow (MW)": 0.0,
            "Displaced Deficit (MW)": unit_rating,
            "Rating (MW)": unit_rating
        })

    c_fail_tab, c_reroute_tab = st.columns([1.1, 1.0])
    with c_fail_tab:
        st.markdown("**1. Severed Lines & Offline Facilities**")
        if failed_rows:
            st.dataframe(pd.DataFrame(failed_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No line outages recorded.")

    with c_reroute_tab:
        st.markdown("**2. Dynamic Edmonds–Karp Rerouting: Surviving Lines Absorbing Load**")
        if rerouted_corridors:
            st.dataframe(pd.DataFrame(rerouted_corridors), use_container_width=True, hide_index=True)
        else:
            idle_severed = [r["Severed Component / Line"] for r in failed_rows if r.get("Pre-Failure Flow (MW)") == 0.0 or r.get("Pre-Failure Flow (MW)") == 0]
            if idle_severed:
                st.info(f"No power rerouting required on transmission mesh at Hour {selected_hour:02d}:00 because the severed line ({', '.join(idle_severed)}) carried 0.0 MW baseline flow at this specific hour. Move the simulation hour slider to hours with active transfers (e.g. evening peak 21:00 or night 04:00) to observe dynamic Edmonds–Karp rerouting.")
            else:
                st.info(f"No inter-substation flow diverted on transmission mesh at Hour {selected_hour:02d}:00. Local generation and storage at substations are serving connected loads directly.")

    # Generation & Storage Contribution Table at this hour
    st.markdown(f"**3. Power Load Distribution at Hour {selected_hour:02d}:00**")
    contrib_df = pd.DataFrame([{
        "Main Generator (MW)": round(float(selected_row.get("Generator used (MW)", 0.0)), 2),
        "Solar Generation (MW)": round(float(selected_row.get("Solar (MW)", 0.0)), 2),
        "Wind Generation (MW)": round(float(selected_row.get("Wind (MW)", 0.0)), 2),
        "Hydro Generation (MW)": round(float(selected_row.get("Hydro (MW)", 0.0)), 2),
        "Hydro Used (MW)": round(float(selected_row.get("Hydro used (MW)", 0.0)), 2),
        "Central Battery Discharge (MW)": round(float(selected_row.get("Battery discharge (MW)", 0.0)), 2),
        "Substation Storage Discharge (MW)": round(float(selected_row.get("Substation storage discharge (MW)", 0.0)), 2),
        "Total Delivered (MW)": round(hour_del, 2),
        "Total Demand (MW)": round(hour_dem, 2),
        "Unserved Deficit (MW)": round(hour_uns, 2),
    }])
    st.dataframe(contrib_df, use_container_width=True, hide_index=True)

else:
    st.info("No transmission line or facility failures active. All grid corridors and power generation assets operating nominally.")

st.divider()

# ==================== 24-HOUR WORKING GRAPH & OPERATIONS TABLE ====================
st.subheader("24-Hour Operations, Generation Mix & Working Schedule")

graph_col, table_col = st.columns([1.3, 1.0])

with graph_col:
    st.markdown("**24-Hour Generation Mix vs Consumer Demand**")
    plot_cols = ["Solar (MW)", "Wind (MW)", "Hydro (MW)", "Generator used (MW)", "Battery discharge (MW)", "Substation storage discharge (MW)", "Demand (MW)"]
    available_cols = [c for c in plot_cols if c in df.columns]
    line_fig = px.line(
        df,
        x="Hour",
        y=available_cols,
        markers=True,
        labels={"value": "Power (MW)", "variable": "Grid Component"},
        color_discrete_map={
            "Solar (MW)": "#f59e0b",
            "Wind (MW)": "#14b8a6",
            "Hydro (MW)": "#06b6d4",
            "Generator used (MW)": "#f97316",
            "Battery discharge (MW)": "#a855f7",
            "Substation storage discharge (MW)": "#10b981",
            "Demand (MW)": "#ef4444"
        }
    )
    line_fig.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=1.14),
        paper_bgcolor="#090d16",
        plot_bgcolor="#090d16",
        font=dict(color="#cbd5e1")
    )
    st.plotly_chart(line_fig, use_container_width=True)

with table_col:
    st.markdown("**24-Hour Battery & Substation Storage Reserve SOC**")
    soc_cols = ["Battery SOC (MWh)", "Substation storage SOC (MWh)"]
    avail_soc = [c for c in soc_cols if c in df.columns]
    soc_fig = px.line(
        df,
        x="Hour",
        y=avail_soc,
        markers=True,
        labels={"value": "Stored Energy (MWh)", "variable": "Storage Asset"},
        color_discrete_map={
            "Battery SOC (MWh)": "#a855f7",
            "Substation storage SOC (MWh)": "#10b981"
        }
    )
    soc_fig.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=1.14),
        paper_bgcolor="#090d16",
        plot_bgcolor="#090d16",
        font=dict(color="#cbd5e1")
    )
    st.plotly_chart(soc_fig, use_container_width=True)

st.markdown("**Complete 24-Hour Operations Telemetry Table**")
display_cols = [
    "Hour", "Demand (MW)", "Delivered (MW)", "Unserved (MW)",
    "Solar (MW)", "Wind (MW)", "Hydro (MW)", "Generator used (MW)",
    "Battery charge (MW)", "Battery discharge (MW)",
    "Substation storage discharge (MW)", "Substation storage charge (MW)",
    "Battery SOC (MWh)", "Substation storage SOC (MWh)", "Operating cost"
]
avail_disp = [c for c in display_cols if c in df.columns]
ops_table = df[avail_disp].copy()
for col in ops_table.columns:
    if col != "Hour":
        ops_table[col] = ops_table[col].round(2)

st.dataframe(ops_table, use_container_width=True, hide_index=True)
