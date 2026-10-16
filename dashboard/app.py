from pathlib import Path
import sys
import time

import plotly.express as px
import streamlit as st

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from dashboard.microgrid import Settings, optimize, simulate
from dashboard.topology import build_topology
from dashboard.network_flow import SOURCE_LINE_CAPACITY, TRANSMISSION_LINES, consumer_feeder_edges

st.set_page_config(page_title="ASI Smart Power Grid", page_icon="⚡", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.1rem;padding-bottom:1.8rem;max-width:1500px}
.hero{padding:1.2rem 1.4rem;border-radius:16px;background:linear-gradient(115deg,#10243b,#174b62);color:#fff;margin-bottom:1rem}
.hero h1{margin:0;font-size:clamp(1.35rem,2.3vw,2rem);line-height:1.22;overflow-wrap:anywhere}
.hero p{margin:.55rem 0 0;color:#d8e7ef;line-height:1.5}
.stMetric{min-width:0;padding:.65rem .75rem;border:1px solid rgba(148,163,184,.2);border-radius:12px;background:rgba(127,127,127,.04)}
[data-testid='stMetricLabel']{white-space:normal;line-height:1.25;min-height:2em}
[data-testid='stMetricValue']{font-size:clamp(1.2rem,2vw,1.8rem);line-height:1.2;overflow-wrap:anywhere}
</style>""", unsafe_allow_html=True)
st.markdown(
    '<div class="hero"><h1>⚡ ASI Smart Power Grid & Microgrid</h1>'
    '<p>Genetic algorithm optimizes battery dispatch • Edmonds–Karp allocates power through the network</p></div>',
    unsafe_allow_html=True,
)
st.caption("Research simulation, not a physical grid controller. Capacities and profiles are illustrative engineering assumptions.")

SOURCE_LINE_OPTIONS = [(src, sub) for src, rows in SOURCE_LINE_CAPACITY.items() for sub in rows]
MESH_LINE_OPTIONS = list(TRANSMISSION_LINES)
FEEDER_OPTIONS = list(consumer_feeder_edges())
LINE_LABEL_MAP = {}
for src, sub in SOURCE_LINE_OPTIONS:
    LINE_LABEL_MAP[f"Transmission line: {src} → {sub}"] = [(src, sub)]
for a, b in MESH_LINE_OPTIONS:
    LINE_LABEL_MAP[f"Transmission corridor: {a} ↔ {b}"] = [(a, b), (b, a)]
for sub, consumer in FEEDER_OPTIONS:
    LINE_LABEL_MAP[f"Consumer feeder: {sub} → {consumer}"] = [(sub, consumer)]
LINE_OPTIONS = list(LINE_LABEL_MAP)

with st.sidebar:
    st.header("Grid scenario")
    demand_scale = st.slider("Demand level", 0.75, 1.35, 1.0, 0.05, key="input_demand")
    solar_scale = st.slider("Solar availability", 0.3, 1.4, 1.0, 0.05, key="input_solar")
    wind_scale = st.slider("Wind availability", 0.3, 1.4, 1.0, 0.05, key="input_wind")
    generator_capacity = st.slider("Main generator capacity (MW)", 60, 220, 150, 5, key="input_generator")
    st.divider()
    st.subheader("Battery storage")
    battery_capacity = st.slider("Battery capacity (MWh)", 40, 240, 120, 10, key="input_battery_capacity")
    battery_power = st.slider("Battery charge/discharge limit (MW)", 10, 60, 35, 5, key="input_battery_power")
    initial_soc = st.slider("Initial battery energy (MWh)", 0, 240, 60, 5, key="input_initial_soc")
    reserve_soc = st.slider("Protected reserve (MWh)", 0, 100, 18, 2, key="input_reserve")
    st.divider()
    st.subheader("ASI genetic algorithm")
    population = st.slider("Population", 8, 32, 8, 4, key="input_population", help="Smaller populations run faster; increase for deeper optimization.")
    generations = st.slider("Generations", 2, 30, 3, 1, key="input_generations", help="More generations may improve the battery schedule but increase runtime.")
    seed = st.number_input("Repeatable random seed", min_value=0, max_value=999999, value=2026, step=1, key="input_seed")
    st.divider()
    st.subheader("Grid failure simulation")
    failure_options = (
        LINE_OPTIONS
        + [f"Substation: {sub}" for sub in SOURCE_LINE_CAPACITY['Battery']]
        + ["Generator: Main Generator"]
        + ["Renewable source: Solar", "Renewable source: Wind"]
    )
    selected_failures = st.multiselect(
        "Components to fail (select multiple)",
        options=failure_options,
        default=[],
        key="failure_components",
        help="Select any combination of transmission lines, substations, the generator, solar, or wind. All selected failures are applied together when you press Run simulation.",
    )
    if selected_failures:
        st.warning(f"{len(selected_failures)} failure(s) selected. They will be applied together on the next run.")
    else:
        st.caption("No component failures selected — normal operation.")

    run = st.button("Run simulation", type="primary", use_container_width=True)

failed_generator = "Generator: Main Generator" in selected_failures
failed_solar = "Renewable source: Solar" in selected_failures
failed_wind = "Renewable source: Wind" in selected_failures

# Keep the unfailed control settings separate. A source outage must be compared
# against normal availability, not against a baseline that also has that source disabled.
normal_settings = Settings(
    demand_scale=float(demand_scale),
    solar_scale=float(solar_scale),
    wind_scale=float(wind_scale),
    generator_capacity=float(generator_capacity),
    battery_capacity=float(battery_capacity),
    battery_power=float(battery_power),
    initial_soc=float(min(initial_soc, battery_capacity)),
    reserve_soc=float(min(reserve_soc, battery_capacity)),
    population=int(population),
    generations=int(generations),
    seed=int(seed),
)
settings = Settings(
    demand_scale=float(demand_scale),
    solar_scale=0.0 if failed_solar else float(solar_scale),
    wind_scale=0.0 if failed_wind else float(wind_scale),
    generator_capacity=0.0 if failed_generator else float(generator_capacity),
    battery_capacity=float(battery_capacity),
    battery_power=float(battery_power),
    initial_soc=float(min(initial_soc, battery_capacity)),
    reserve_soc=float(min(reserve_soc, battery_capacity)),
    population=int(population),
    generations=int(generations),
    seed=int(seed),
)
line_overrides = {}
substation_overrides = {}
feeder_overrides = {}
failed_visual_edges = set()
for failure in selected_failures:
    if failure in LINE_LABEL_MAP:
        for edge in LINE_LABEL_MAP[failure]:
            if edge[0] in SOURCE_LINE_CAPACITY and edge[1] in SOURCE_LINE_CAPACITY[edge[0]]:
                line_overrides[edge] = 0.0
            elif edge[0].startswith("S") and edge[1].startswith("S"):
                line_overrides[edge] = 0.0
            else:
                feeder_overrides[edge] = 0.0
            failed_visual_edges.add(edge)
    elif failure.startswith("Substation: "):
        substation_overrides[failure.removeprefix("Substation: ")] = 0.0
    elif failure == "Generator: Main Generator":
        failed_source_edges = [("Main Generator", sub) for sub in SOURCE_LINE_CAPACITY["Main Generator"]]
        line_overrides.update({edge: 0.0 for edge in failed_source_edges})
        failed_visual_edges.update(failed_source_edges)
    elif failure == "Renewable source: Solar":
        failed_source_edges = [("Solar", sub) for sub in SOURCE_LINE_CAPACITY["Solar"]]
        line_overrides.update({edge: 0.0 for edge in failed_source_edges})
        failed_visual_edges.update(failed_source_edges)
    elif failure == "Renewable source: Wind":
        failed_source_edges = [("Wind", sub) for sub in SOURCE_LINE_CAPACITY["Wind"]]
        line_overrides.update({edge: 0.0 for edge in failed_source_edges})
        failed_visual_edges.update(failed_source_edges)

# Slider changes rerun the Streamlit script but do not rerun the expensive simulation.
# Only the explicit Run simulation button commits a new result (apart from first page load).
should_run = run or "asi_result" not in st.session_state
if should_run:
    started_at = time.perf_counter()
    with st.spinner("ASI is optimizing the 24-hour battery schedule and routing power through the network..."):
        actions, result = optimize(
            settings,
            seed=int(seed),
            line_capacity_overrides=line_overrides,
            substation_capacity_overrides=substation_overrides,
            feeder_capacity_overrides=feeder_overrides,
        )
        # Controlled reference: same profiles and battery schedule, no outages.
        baseline_result = simulate(actions, normal_settings, seed=int(seed))
    run_seconds = time.perf_counter() - started_at
    st.session_state["run_seconds"] = run_seconds
    st.session_state["asi_result"] = result
    st.session_state["baseline_result"] = baseline_result
    st.session_state["actions"] = actions
    st.session_state["run_settings"] = settings
    st.session_state["run_line_overrides"] = dict(line_overrides)
    st.session_state["run_substation_overrides"] = dict(substation_overrides)
    st.session_state["run_feeder_overrides"] = dict(feeder_overrides)
    st.session_state["run_visual_edges"] = set(failed_visual_edges)
    st.session_state["run_failure_label"] = (
        "; ".join(selected_failures) if selected_failures else "None — normal operation"
    )
    st.session_state["run_selected_failures"] = list(selected_failures)

asi = st.session_state["asi_result"]
applied_settings = st.session_state["run_settings"]
df = asi["hourly"]
last_failure = st.session_state.get("run_failure_label", "None — normal operation")

if settings != applied_settings or line_overrides != st.session_state.get("run_line_overrides", {}) or substation_overrides != st.session_state.get("run_substation_overrides", {}) or feeder_overrides != st.session_state.get("run_feeder_overrides", {}) or selected_failures != st.session_state.get("run_selected_failures", []):
    st.info("Settings changed but not yet simulated. Press **Run simulation** to apply them. The results below are from the last completed run.")
else:
    st.caption(f"Last completed simulation · Applied grid failure: {last_failure} · Runtime: {st.session_state.get('run_seconds', 0.0):.2f} s")

st.subheader("System performance — optimized for selected scenario")
st.caption("These metrics use a battery schedule optimized for the currently selected scenario. Comparing this value with a previous run can be misleading because the genetic algorithm may choose a different schedule. Use the controlled comparison below to isolate the network-failure effect at identical battery actions.")
metric_rows = [
    ("Operating cost", f"${asi['cost']:,.0f}"),
    ("Unserved energy", f"{asi['unserved']:.2f} MWh"),
    ("Energy delivered", f"{asi['delivered']:,.1f} MWh"),
    ("Final battery energy", f"{asi['final_soc']:.1f} MWh"),
    ("Generator energy", f"{asi['generator']:,.1f} MWh"),
    ("Battery throughput", f"{asi['throughput']:.1f} MWh"),
    ("Renewable curtailed", f"{asi['curtailment']:.1f} MWh"),
    ("Critical-load service", f"{asi['critical_service_pct']:.1f}%"),
]
for start in (0, 4):
    cols = st.columns(4)
    for col, (label, value) in zip(cols, metric_rows[start:start + 4]):
        col.metric(label, value)
# Explain why system metrics may remain unchanged after an outage selection.
# This compares the outage run with a no-outage run using the exact same battery actions.
baseline = st.session_state.get("baseline_result")
if baseline is not None:
    st.subheader("Failure impact vs. same dispatch without failures")
    st.caption("Controlled comparison: the failed and no-failure runs use the same battery actions and seed. This is the correct comparison for isolating the effect of the selected network failures.")
    consumer_delivery_columns = [f"C{i:03d} delivered (MW)" for i in range(1, 51)]
    current_consumers = asi["hourly"][consumer_delivery_columns].to_numpy(dtype=float)
    reference_consumers = baseline["hourly"][consumer_delivery_columns].to_numpy(dtype=float)
    consumer_delta = current_consumers - reference_consumers
    affected_consumer_count = int((abs(consumer_delta).sum(axis=0) > 1e-5).sum())
    allocation_shift = float(abs(consumer_delta).sum())
    impact_cols = st.columns(5)
    comparisons = [
        ("Energy delivered", float(asi["delivered"]), float(baseline["delivered"]), "MWh"),
        ("Unserved energy", float(asi["unserved"]), float(baseline["unserved"]), "MWh"),
        ("Operating cost", float(asi["cost"]), float(baseline["cost"]), "$"),
    ]
    for col, (label, current, reference, unit) in zip(impact_cols, comparisons):
        delta = current - reference
        if unit == "$":
            col.metric(label, f"${current:,.0f}", delta=f"${delta:+,.0f}")
        else:
            col.metric(label, f"{current:,.2f} {unit}", delta=f"{delta:+,.2f} {unit}", delta_color="inverse" if label == "Unserved energy" else "normal")
    impact_cols[3].metric("Consumers affected", f"{affected_consumer_count}/50")
    impact_cols[4].metric("Consumer energy shifted", f"{allocation_shift:.2f} MWh")
    measurable_impact = any(abs(current-reference) > 1e-5 for _, current, reference, _ in comparisons)
    consumer_impact = affected_consumer_count > 0
    if last_failure == "None — normal operation":
        st.info("Normal-operation run: no outages are selected.")
    elif float(asi["unserved"]) + 1e-4 < float(baseline["unserved"]):
        st.error("Consistency warning: the constrained run reports less unserved energy than the same-dispatch no-failure run. Inspect the engine output and flow audit before interpreting this as resilience.")
    elif measurable_impact or consumer_impact:
        st.success("Failure impact calculated. Aggregate energy/cost can remain unchanged when redundancy preserves total service; consumer-level allocation changes are reported separately.")
    else:
        st.info("No measurable impact for this dispatch: aggregate results and individual consumer allocations are unchanged. The failed components may have carried no power, or alternate routes may have had sufficient spare capacity. Check edge-flow diagnostics and the exported CSV.")

st.caption(
    f"Critical consumers served: {asi['critical_delivered']:,.1f} MWh of "
    f"{asi['critical_demand']:,.1f} MWh requested."
)
if last_failure != "None — normal operation":
    st.warning(f"Failure scenario applied in the displayed results: **{last_failure}**")

st.subheader("Grid topology")
selected_hour = st.slider("Inspect grid at hour", 0, 23, 18, 1, key="inspect_hour")
selected_row = df.iloc[selected_hour]
districts = {f"D{i}": float(selected_row.get(f"D{i} delivered (MW)", 0.0)) for i in range(1, 9)}
district_demand = {f"D{i}": float(selected_row.get(f"D{i} demand (MW)", 0.0)) for i in range(1, 9)}
st.caption(
    "50 individually modeled consumers • 8 substations • 16 inter-substation corridors • "
    "two independent feeder connections per consumer. Red dashed connections indicate selected failed routes."
)
topology_hour_data = {"delivered": districts, "demand": district_demand}
for consumer_index in range(1, 51):
    consumer = f"C{consumer_index:03d}"
    topology_hour_data[f"{consumer} delivered (MW)"] = float(selected_row.get(f"{consumer} delivered (MW)", 0.0))
    topology_hour_data[f"{consumer} demand (MW)"] = float(selected_row.get(f"{consumer} demand (MW)", 0.0))
st.plotly_chart(
    build_topology(topology_hour_data,
                   failed_edges=st.session_state.get("run_visual_edges", set()),
                   failed_substations=set(st.session_state.get("run_substation_overrides", {}))),
    use_container_width=True,
    config={"displayModeBar": False},
)
st.caption("Consumer markers: green = fully served, amber = partially served, red = unserved. Failed network connections are shown as red dashed lines.")
consumer_rows = []
for consumer_index in range(1, 51):
    consumer = f"C{consumer_index:03d}"
    demand_value = float(selected_row.get(f"{consumer} demand (MW)", 0.0))
    delivered_value = float(selected_row.get(f"{consumer} delivered (MW)", 0.0))
    consumer_rows.append({"Consumer": consumer, "Priority": "Critical" if consumer_index in {3,10,17,24,31,38,45} else "Standard",
                         "Demand (MW)": demand_value, "Delivered (MW)": delivered_value,
                         "Unserved (MW)": max(0.0, demand_value-delivered_value)})
with st.expander(f"Consumer-level service at hour {selected_hour} (50 consumers)"):
    st.dataframe(__import__("pandas").DataFrame(consumer_rows).round(2), use_container_width=True, hide_index=True)
with st.expander(f"Feeder capacity and flow diagnostics at hour {selected_hour}"):
    feeder_diagnostics = []
    feeder_definitions = consumer_feeder_edges()
    for consumer_index in range(1, 51):
        consumer = f"C{consumer_index:03d}"
        for (sub, endpoint), capacity in feeder_definitions.items():
            if endpoint != consumer:
                continue
            capacity_col = f"Feeder {sub} -> {consumer} capacity (MW)"
            flow_col = f"Feeder {sub} -> {consumer} flow (MW)"
            effective_capacity = float(selected_row.get(capacity_col, capacity))
            flow = float(selected_row.get(flow_col, 0.0))
            feeder_diagnostics.append({"Consumer": consumer, "Feeder": f"{sub} → {consumer}",
                "Status": "FAILED / isolated" if effective_capacity <= 1e-9 else "Available",
                "Capacity (MW)": effective_capacity, "Flow (MW)": flow})
    st.dataframe(__import__("pandas").DataFrame(feeder_diagnostics).round(3), use_container_width=True, hide_index=True)

st.caption(
    f"Hour {selected_hour}: {selected_row['Delivered (MW)']:.1f} MW delivered of "
    f"{selected_row['Demand (MW)']:.1f} MW demand; generator output "
    f"{selected_row['Generator used (MW)']:.1f} MW; battery discharge "
    f"{selected_row['Battery discharge (MW)']:.1f} MW."
)

left, right = st.columns([1.25, 1])
with left:
    st.subheader("24-hour power dispatch")
    energy_columns = ["Solar (MW)", "Wind (MW)", "Battery discharge (MW)", "Generator used (MW)", "Delivered (MW)"]
    dispatch_fig = px.line(df, x="Hour", y=energy_columns, labels={"value": "Power / delivered load (MW)", "variable": "Series"}, markers=True)
    dispatch_fig.update_layout(height=360, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(dispatch_fig, use_container_width=True)
with right:
    st.subheader("Battery state of charge")
    soc_fig = px.area(df, x="Hour", y="Battery SOC (MWh)", labels={"Battery SOC (MWh)": "Stored energy (MWh)"})
    soc_fig.add_hline(y=applied_settings.reserve_soc, line_dash="dash", annotation_text="Protected reserve")
    soc_fig.update_layout(height=360, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(soc_fig, use_container_width=True)

st.subheader("Hourly simulation results")
base_hourly_columns = ["Hour", "Demand (MW)", "Solar (MW)", "Wind (MW)", "Battery charge (MW)", "Battery discharge (MW)", "Generator used (MW)", "Delivered (MW)", "Unserved (MW)", "Battery SOC (MWh)", "Operating cost"] + [f"D{i} delivered (MW)" for i in range(1,9)]
st.dataframe(df[base_hourly_columns].round(2), use_container_width=True, hide_index=True)
# Export the exact last-completed run, including consumer-level unmet demand and scenario metadata.
# The UI controls may have changed since the last run; use only committed session-state values.
export_df = df.copy()
for consumer_index in range(1, 51):
    consumer = f"C{consumer_index:03d}"
    demand_col = f"{consumer} demand (MW)"
    delivered_col = f"{consumer} delivered (MW)"
    if demand_col in export_df.columns and delivered_col in export_df.columns:
        export_df[f"{consumer} unserved (MW)"] = (
            export_df[demand_col].astype(float) - export_df[delivered_col].astype(float)
        ).clip(lower=0.0)
export_df.insert(0, "Applied failure scenario", st.session_state.get("run_failure_label", "None — normal operation"))
export_df.insert(1, "Applied failure count", len(st.session_state.get("run_selected_failures", [])))
export_df.insert(2, "Applied seed", int(applied_settings.seed))
export_df.insert(3, "GA population", int(applied_settings.population))
export_df.insert(4, "GA generations", int(applied_settings.generations))
export_df.insert(5, "Run runtime (s)", float(st.session_state.get("run_seconds", 0.0)))
export_df.insert(6, "Demand scale", float(applied_settings.demand_scale))
export_df.insert(7, "Solar scale", float(applied_settings.solar_scale))
export_df.insert(8, "Wind scale", float(applied_settings.wind_scale))
export_df.insert(9, "Generator capacity setting (MW)", float(applied_settings.generator_capacity))
st.download_button(
    "Download full hourly + 50-consumer results (CSV)",
    export_df.to_csv(index=False, float_format="%.6f").encode("utf-8"),
    "asi_microgrid_hourly_results.csv",
    "text/csv",
    help="Includes each consumer's hourly demand, delivered power and unserved power, plus the failure scenario used for the displayed results.",
)
st.markdown("---")
st.markdown("""**How the ASI simulation works**
1. The genetic algorithm selects one battery action for each of 24 hours.
2. The dispatch model enforces battery energy, reserve, efficiency and charge/discharge limits; charging uses renewable surplus only.
3. Edmonds–Karp routes power across source links, the meshed eight-substation transmission network, and two feeder routes for each of 50 modeled consumers.
4. Multiple simultaneous source-line, transmission-corridor, consumer-feeder, substation, generator, and renewable failures are applied to the network capacities before rerouting.
5. Seven critical consumers receive the first allocation pass; residual network capacity then serves noncritical consumers.

*This is a constrained network-flow resilience simulation, not a full AC power-flow model. Voltage, frequency and electrical dynamics are not solved.*""")
