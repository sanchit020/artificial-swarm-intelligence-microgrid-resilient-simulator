"""High-Tech Cyber-Physical SCADA Grid Cartography for the ASI Microgrid.

Visualizes 50 individually modeled consumers, 8 substation intelligent agents,
16 mesh transmission corridors, and distributed energy generation/storage assets.
Features interactive dynamic zoom, flow-rate glow channels, and failure diagnostics.
"""
import math
import numpy as np
import plotly.graph_objects as go

# Modern High-Tech SCADA Palette
COLORS = {
    "solar": "#f59e0b",       # Radiant Solar Gold
    "wind": "#14b8a6",        # Clean Cyan Teal
    "hydro": "#06b6d4",       # Hydro Electric Cyan
    "battery": "#a855f7",     # High-Voltage Purple
    "sub_storage": "#10b981", # Substation Local Storage Emerald
    "generator": "#f97316",   # Thermal Core Orange
    "substation": "#00d2ff",  # SCADA Cyan Node
    "critical": "#f43f5e",    # Emergency Ruby Red
    "consumer": "#94a3b8"     # Standard Slate
}

def _asset_nodes():
    rng = np.random.default_rng(41)
    nodes = {}
    # Distributed power generation/storage throughout the territory
    for prefix, kind, count in [("Solar", "solar", 10), ("Wind", "wind", 8),
                                ("Battery", "battery", 8), ("Gen", "generator", 12)]:
        for i in range(1, count + 1):
            x = float(rng.uniform(7, 93))
            y = float(rng.uniform(8, 92))
            nodes[f"{prefix} {i:02d}"] = (x, y, kind)

    # 8 modeled substations forming the resilient backbone mesh
    sub_positions = {
        "S1": (31, 72), "S2": (48, 78), "S3": (67, 69), "S4": (76, 49),
        "S5": (65, 29), "S6": (45, 22), "S7": (27, 34), "S8": (49, 49)
    }
    for n, (x, y) in sub_positions.items():
        nodes[n] = (x, y, "substation")

    # 50 consumers individually represented in the solver model
    for i in range(1, 51):
        x = float(rng.uniform(7, 94))
        y = float(rng.uniform(7, 93))
        if i % 3 == 0:
            cx, cy = [(25, 65), (48, 55), (72, 40), (35, 28), (70, 75)][(i // 3) % 5]
            x = float(np.clip(rng.normal(cx, 8), 5, 96))
            y = float(np.clip(rng.normal(cy, 7), 5, 96))
        kind = "critical" if i in (3, 10, 17, 24, 31, 38, 45) else "consumer"
        nodes[f"C{i:03d}"] = (x, y, kind)

    # Hydro assets situated near river and reservoir substations S4 (76, 49) and S5 (65, 29)
    nodes["Hydro 01"] = (79.0, 52.0, "hydro")
    nodes["Hydro 02"] = (82.0, 46.0, "hydro")
    nodes["Hydro 03"] = (69.0, 31.0, "hydro")
    nodes["Hydro 04"] = (63.0, 26.0, "hydro")

    return nodes, sub_positions

NODES, SUB_POS = _asset_nodes()

def _nearest_sub(x, y):
    return min(SUB_POS, key=lambda s: (SUB_POS[s][0] - x)**2 + (SUB_POS[s][1] - y)**2)

def _nearest_two_subs(x, y):
    return sorted(SUB_POS, key=lambda s: (SUB_POS[s][0] - x)**2 + (SUB_POS[s][1] - y)**2)[:2]

def _draw_scada_background(fig):
    """Draws a sleek cyber-physical SCADA coordinate grid canvas."""
    # Subtle coordinate grid lines
    for gx in range(10, 100, 10):
        fig.add_trace(go.Scatter(
            x=[gx, gx], y=[5, 95], mode="lines",
            line=dict(color="rgba(30, 41, 59, 0.45)", width=0.8, dash="dot"),
            hoverinfo="skip", showlegend=False
        ))
    for gy in range(10, 100, 10):
        fig.add_trace(go.Scatter(
            x=[5, 95], y=[gy, gy], mode="lines",
            line=dict(color="rgba(30, 41, 59, 0.45)", width=0.8, dash="dot"),
            hoverinfo="skip", showlegend=False
        ))

    # Concentric range rings from central hub S8 (49, 49)
    cx, cy = 49.0, 49.0
    for radius in [18.0, 32.0, 44.0]:
        theta = np.linspace(0, 2 * np.pi, 90)
        xs = cx + radius * np.cos(theta)
        ys = cy + radius * np.sin(theta)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color="rgba(56, 189, 248, 0.10)", width=1.0, dash="dash"),
            hoverinfo="skip", showlegend=False
        ))

    # Tactical Sector Callouts
    sectors = [
        (22, 88, "[ SECTOR 1 • NORTH-WEST MESH ]"),
        (75, 88, "[ SECTOR 2 • NORTH-EAST GENERATION ]"),
        (82, 38, "[ SECTOR 3 • EASTERN INDUSTRIAL VALLEY ]"),
        (20, 18, "[ SECTOR 4 • SOUTH-WEST COASTAL ]"),
        (70, 16, "[ SECTOR 5 • SOUTHERN CORRIDOR ]"),
    ]
    for sx, sy, label in sectors:
        fig.add_annotation(
            x=sx, y=sy, text=label, showarrow=False,
            font=dict(size=8.5, color="rgba(148, 163, 184, 0.50)", family="monospace")
        )

def build_topology(hour_row=None, failed_edges=None, failed_substations=None,
                   failed_facilities=None,
                   view_focus="mesh", show_feeders=True, show_assets=True,
                   map_size="standard"):
    fig = go.Figure()
    failed_edges = set(failed_edges or [])
    failed_substations = set(failed_substations or [])
    failed_facilities = set(failed_facilities or [])
    row = hour_row or {}
    pos = {n: (v[0], v[1]) for n, v in NODES.items()}

    _draw_scada_background(fig)

    # 1. Distributed generation asset conduit links
    if show_assets:
        asset_names = [n for n, (_, _, k) in NODES.items() if k in ("solar", "wind", "hydro", "battery", "generator")]
        for n in asset_names:
            x, y, kind = NODES[n]
            source_class = {"solar": "Solar", "wind": "Wind", "hydro": "Hydro", "battery": "Battery", "generator": "Main Generator"}[kind]
            for sub in _nearest_two_subs(x, y):
                sx, sy = SUB_POS[sub]
                col = COLORS[kind]
                is_line_failed = (
                    n in failed_facilities
                    or (n, sub) in failed_edges
                    or (source_class, sub) in failed_edges
                    or sub in failed_substations
                )
                source_flow = float(row.get(f"Source line {source_class} -> {sub} flow (MW)", 0.0))

                if is_line_failed:
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color="#ef4444", width=2.4, dash="dash"),
                        opacity=0.90, hoverinfo="text",
                        text=f"<b>{n} → {sub}</b><br>Status: [OFFLINE / SEVERED] (0.0 MW)",
                        showlegend=False
                    ))
                elif source_flow > 0.05:
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color=col, width=2.4, dash="solid"),
                        opacity=0.80, hoverinfo="text",
                        text=f"<b>{n} → {sub}</b><br>Status: [INJECTING POWER]<br>Flow: <b>{source_flow:.1f} MW</b>",
                        showlegend=False
                    ))
                else:
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color=col, width=1.0, dash="dot"),
                        opacity=0.25, hoverinfo="text",
                        text=f"<b>{n} → {sub}</b><br>Status: [STANDBY]",
                        showlegend=False
                    ))

    # 2. 16 Transmission Backbone Mesh Corridors
    mesh = [
        ("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5"), ("S5", "S6"), ("S6", "S7"),
        ("S7", "S1"), ("S1", "S8"), ("S2", "S8"), ("S3", "S8"), ("S4", "S8"), ("S5", "S8"),
        ("S6", "S8"), ("S7", "S8"), ("S2", "S6"), ("S3", "S5")
    ]

    for u, v in mesh:
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        failed = (u, v) in failed_edges or (v, u) in failed_edges or u in failed_substations or v in failed_substations
        flow_uv = float(row.get(f"Transmission {u} -> {v} flow (MW)", 0.0))
        flow_vu = float(row.get(f"Transmission {v} -> {u} flow (MW)", 0.0))
        abs_flow = max(flow_uv, flow_vu)

        if failed:
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color="#ef4444", width=4.0, dash="dash"),
                opacity=0.95, hoverinfo="text",
                text=f"<b>Corridor {u} - {v}</b><br>Status: [TRIPPED / SEVERED]<br>Flow: 0.0 MW (Cap: 0.0 / 48.0 MW)",
                showlegend=False
            ))
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            fig.add_annotation(
                x=mx, y=my,
                text=f"{u}-{v}<br><b>[SEVERED]</b>",
                showarrow=False,
                font=dict(size=9, color="#fca5a5", family="sans-serif"),
                bgcolor="rgba(69, 10, 10, 0.94)",
                bordercolor="#ef4444",
                borderwidth=1.5,
                borderpad=3,
            )
        elif abs_flow > 0.05:
            direction = f"{u} → {v}" if flow_uv >= flow_vu else f"{v} → {u}"
            load_pct = (abs_flow / 48.0) * 100.0
            is_heavy = load_pct >= 75.0
            line_color = "#f59e0b" if is_heavy else "#00f0ff"
            glow_color = "rgba(245, 158, 11, 0.25)" if is_heavy else "rgba(0, 240, 255, 0.25)"
            line_w = 2.8 + min(5.0, 5.0 * (abs_flow / 36.0))

            # Ambient glow underlayer
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=glow_color, width=line_w + 4.5),
                hoverinfo="skip", showlegend=False
            ))
            # Core illuminated line
            hover_text = (
                f"<b>Corridor {u} - {v}</b><br>"
                f"Status: [ACTIVE TRANSMISSION]<br>"
                f"Rerouted Direction: <b>{direction}</b><br>"
                f"Transferred Power: <b>{abs_flow:.2f} MW</b><br>"
                f"Thermal Loading: <b>{load_pct:.1f}%</b> (Rating: 48.0 MW)"
            )
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=line_color, width=line_w),
                opacity=0.95, hoverinfo="text", text=hover_text, showlegend=False
            ))

            # Direct on-map power badge
            if abs_flow >= 0.8:
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                fig.add_annotation(
                    x=mx, y=my,
                    text=f"{direction}<br><b>{abs_flow:.1f} MW</b>",
                    showarrow=False,
                    font=dict(size=9, color="#e0f2fe", family="monospace"),
                    bgcolor="rgba(11, 19, 41, 0.94)",
                    bordercolor=line_color,
                    borderwidth=1.5,
                    borderpad=3,
                )
        else:
            hover_text = f"<b>Corridor {u} - {v}</b><br>Status: [STANDBY]<br>Available Capacity: 48.0 MW"
            fig.add_trace(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color="rgba(148, 163, 184, 0.35)", width=1.8),
                opacity=0.50, hoverinfo="text", text=hover_text, showlegend=False
            ))

    # 3. Dual Redundant Feeders (100 distribution lines)
    if show_feeders:
        for n, (x, y, kind) in NODES.items():
            if kind not in ("consumer", "critical"):
                continue
            for sub in _nearest_two_subs(x, y):
                sx, sy = SUB_POS[sub]
                failed = (sub, n) in failed_edges or sub in failed_substations
                feeder_flow = float(row.get(f"Feeder {sub} -> {n} flow (MW)", 0.0))

                if failed:
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color="#ef4444", width=2.0, dash="dash"),
                        opacity=0.85, hoverinfo="text",
                        text=f"Feeder {sub} → {n}<br>Status: [SEVERED] (0.0 MW)",
                        showlegend=False
                    ))
                elif feeder_flow > 0.01:
                    fw = 1.6 + min(2.2, 2.2 * (feeder_flow / 4.0))
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color="rgba(56, 189, 248, 0.70)", width=fw),
                        opacity=0.75, hoverinfo="text",
                        text=f"Feeder {sub} → {n}<br>Status: [ACTIVE DELIVERY]<br>Flow: <b>{feeder_flow:.2f} MW</b>",
                        showlegend=False
                    ))
                else:
                    fig.add_trace(go.Scatter(
                        x=[x, sx], y=[y, sy], mode="lines",
                        line=dict(color="rgba(148, 163, 184, 0.18)", width=1.0),
                        opacity=0.20, hoverinfo="text",
                        text=f"Feeder {sub} → {n}<br>Status: [STANDBY]",
                        showlegend=False
                    ))

    # 4. Markers for Nodes
    classes = [
        ("Solar Parks", "solar", "solar"),
        ("Wind Turbines", "wind", "wind"),
        ("Hydro Power", "hydro", "hydro"),
        ("Battery Storage", "battery", "battery"),
        ("Thermal Generators", "generator", "generator"),
        ("Substation Hubs", "substation", "substation"),
        ("Critical Facilities", "critical", "critical"),
        ("Standard Consumers", "consumer", "consumer")
    ]

    for legend, kind, color_key in classes:
        if not show_assets and kind in ("solar", "wind", "hydro", "battery", "generator"):
            continue

        names = [n for n, (_, _, k) in NODES.items() if k == kind]
        xs = [pos[n][0] for n in names]
        ys = [pos[n][1] for n in names]
        sizes = {
            "solar": 13, "wind": 13, "hydro": 14, "battery": 15, "generator": 16,
            "substation": 30, "critical": 14, "consumer": 8
        }
        labels = [n if kind == "substation" else "" for n in names]
        custom = []
        marker_colors = []

        if kind == "substation":
            for n in names:
                dist = n.replace("S", "D")
                dist_mw = float(row.get(f"{dist} delivered (MW)", 0.0))
                ang = float(row.get(f"Bus {n} angle (deg)", 0.0))
                v_pu = float(row.get(f"Bus {n} voltage (pu)", 1.0))
                sub_storage_dis = float(row.get("Substation storage discharge (MW)", 0.0))
                if n in failed_substations:
                    marker_colors.append("#ef4444")
                    custom.append(f"<b>Substation {n}</b><br>Status: [OFFLINE / FAILED]<br>All feeder links severed!")
                else:
                    marker_colors.append("#00d2ff")
                    custom.append(
                        f"<b>Substation Agent {n}</b><br>"
                        f"Status: [ONLINE & SYNCHRONIZED]<br>"
                        f"District {dist} Flow: <b>{dist_mw:.1f} MW</b><br>"
                        f"Local Substation Storage: <b>15.0 MWh</b> (Discharging: {sub_storage_dis:.1f} MW)<br>"
                        f"Voltage Angle: <b>{ang:+.2f}°</b> | Magnitude: <b>{v_pu:.3f} p.u.</b><br>"
                        f"Throughput Rating: <b>82.0 MW</b>"
                    )
        elif kind in ("consumer", "critical"):
            for n in names:
                demand = float(row.get(f"{n} demand (MW)", 0.0))
                delivered = float(row.get(f"{n} delivered (MW)", 0.0))
                unserved = max(0.0, demand - delivered)
                ratio = delivered / max(demand, 1e-9)
                prio_str = "Critical Facility (Priority 1)" if kind == "critical" else "Standard Consumer"
                if ratio >= 0.999:
                    marker_colors.append("#10b981")
                    status_str = "[100% SERVED] Fully Powered"
                elif ratio > 0.001:
                    marker_colors.append("#f59e0b")
                    status_str = f"[PARTIAL] ({ratio*100:.1f}%)"
                else:
                    marker_colors.append("#ef4444")
                    status_str = "[BLACKOUT] Zero Delivery"

                nearest = _nearest_two_subs(pos[n][0], pos[n][1])
                custom.append(
                    f"<b>{n} • {prio_str}</b><br>"
                    f"Status: <b>{status_str}</b><br>"
                    f"Delivered: <b>{delivered:.2f} MW</b> / {demand:.2f} MW<br>"
                    f"Unserved: <b>{unserved:.2f} MW</b><br>"
                    f"Dual Feeders: {nearest[0]}, {nearest[1]}"
                )
        else:
            for n in names:
                x, y, k = NODES[n]
                if n in failed_facilities:
                    marker_colors.append("#ef4444")
                    custom.append(
                        f"<b>{n} • {kind.title()} Facility</b><br>"
                        f"Status: <b>[FACILITY OFFLINE / TRIPPED]</b><br>"
                        f"All connecting power conduits severed (0.0 MW)<br>"
                        f"Nearest Substation: {_nearest_sub(x, y)}"
                    )
                else:
                    marker_colors.append(COLORS[color_key])
                    custom.append(f"<b>{n}</b><br>Asset Class: {kind.title()}<br>Nearest Substation: {_nearest_sub(x, y)}")

        # Draw nodes
        marker_symbol = "diamond" if kind == "critical" else "circle"
        marker_line_color = "#ffffff" if kind in ("substation", "critical") else "rgba(255, 255, 255, 0.7)"
        marker_line_width = 2.0 if kind in ("substation", "critical") else 1.2

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers+text" if kind == "substation" else "markers",
            text=labels,
            textposition="middle center",
            textfont=dict(color="#090d16", size=11, family="sans-serif"),
            marker=dict(
                size=sizes[kind],
                color=marker_colors,
                symbol=marker_symbol,
                line=dict(color=marker_line_color, width=marker_line_width),
                opacity=0.98
            ),
            name=legend,
            customdata=custom,
            hovertemplate="%{customdata}<extra></extra>"
        ))

    # Determine view bounds based on zoom focus
    if view_focus in ("mesh", "zoom", "core"):
        # Tightly cropped around the 8 substations and 16 transmission corridors (2.5x zoom)
        range_x = [18.0, 84.0]
        range_y = [15.0, 85.0]
    elif view_focus == "north":
        range_x = [23.0, 80.0]
        range_y = [45.0, 85.0]
    elif view_focus == "south":
        range_x = [20.0, 76.0]
        range_y = [15.0, 58.0]
    else:  # "full"
        range_x = [5.0, 95.0]
        range_y = [5.0, 95.0]

    fig_height = 880 if map_size == "expanded" else (560 if map_size == "compact" else 720)

    fig.update_layout(
        height=fig_height,
        margin=dict(l=0, r=0, t=10, b=10),
        paper_bgcolor="#090d16",
        plot_bgcolor="#090d16",
        font=dict(family="'Inter', -apple-system, sans-serif", size=10, color="#e2e8f0"),
        showlegend=True,
        legend=dict(
            orientation="h",
            y=1.02,
            x=0.5,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(11, 19, 41, 0.88)",
            bordercolor="rgba(56, 189, 248, 0.35)",
            borderwidth=1,
        ),
        xaxis=dict(
            visible=False,
            range=range_x,
            fixedrange=False,  # Enables interactive mouse-wheel zoom and drag-pan!
        ),
        yaxis=dict(
            visible=False,
            range=range_y,
            fixedrange=False,  # Enables interactive mouse-wheel zoom and drag-pan!
            scaleanchor="x",
            scaleratio=1
        ),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.96)",
            bordercolor="#00f0ff",
            font=dict(family="'Inter', sans-serif", size=11, color="#ffffff")
        )
    )
    return fig
