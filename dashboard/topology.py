"""Distributed, fantasy-cartography-inspired visualization of the synthetic grid.

The map visualizes 50 individually modeled consumers and distributed energy asset markers.
The solver models each consumer and feeder individually; generation assets are illustrative
markers for aggregated solar, wind, battery, and generator source classes.
"""
import math
import numpy as np
import plotly.graph_objects as go

COLORS = {
    "solar": "#e7b64c", "wind": "#36c6b0", "battery": "#c28cf4",
    "generator": "#ff9468", "substation": "#55a8ee",
    "critical": "#f26b7a", "consumer": "#aeb8c6"
}
def _asset_nodes():
    rng=np.random.default_rng(41)
    nodes={}
    # Distributed power generation/storage throughout the region.
    for prefix,kind,count in [("Solar","solar",10),("Wind","wind",8),
                              ("Battery","battery",8),("Gen","generator",12)]:
        for i in range(1,count+1):
            # Distribute around the whole map, with a mild regional clustering.
            x=float(rng.uniform(7,93)); y=float(rng.uniform(8,92))
            nodes[f"{prefix} {i:02d}"]=(x,y,kind)
    # Eight modeled substations form a mesh through the whole territory.
    sub_positions={"S1":(31,72),"S2":(48,78),"S3":(67,69),"S4":(76,49),
                   "S5":(65,29),"S6":(45,22),"S7":(27,34),"S8":(49,49)}
    for n,(x,y) in sub_positions.items(): nodes[n]=(x,y,"substation")
    # 50 consumers, individually represented in the numerical model.
    for i in range(1,51):
        x=float(rng.uniform(7,94)); y=float(rng.uniform(7,93))
        # Slightly cluster consumers into settlements without imposing a left/right split.
        if i%3==0:
            cx,cy=[(25,65),(48,55),(72,40),(35,28),(70,75)][(i//3)%5]
            x=float(np.clip(rng.normal(cx,8),5,96)); y=float(np.clip(rng.normal(cy,7),5,96))
        kind="critical" if i in (3,10,17,24,31,38,45) else "consumer"
        nodes[f"C{i:03d}"]=(x,y,kind)
    return nodes,sub_positions

NODES,SUB_POS=_asset_nodes()
def _nearest_sub(x,y):
    return min(SUB_POS,key=lambda s:(SUB_POS[s][0]-x)**2+(SUB_POS[s][1]-y)**2)

def _nearest_two_subs(x,y):
    return sorted(SUB_POS,key=lambda s:(SUB_POS[s][0]-x)**2+(SUB_POS[s][1]-y)**2)[:2]

def _landscape(fig):
    # Original fictional landmasses, drawn as soft parchment-colored polygons.
    land=[
      ([4,12,20,27,32,29,22,17,10,4],[72,85,88,80,68,58,55,61,63,72]),
      ([26,34,44,51,57,54,47,39,31,26],[87,94,91,84,76,66,65,73,78,87]),
      ([58,66,76,88,96,94,86,79,70,62,58],[84,91,88,79,70,58,55,62,65,75,84]),
      ([7,16,25,31,35,32,23,15,8,7],[42,49,45,36,25,17,18,27,33,42]),
      ([40,48,57,66,74,80,77,68,60,50,43,40],[38,47,48,41,33,24,14,10,16,18,27,38]),
      ([79,87,95,97,91,84,79],[45,48,40,30,23,29,45])]
    for xs,ys in land:
        fig.add_trace(go.Scatter(x=xs,y=ys,mode="lines",fill="toself",
            fillcolor="rgba(197,166,112,0.13)",line=dict(color="rgba(218,190,139,0.42)",width=1.4),
            hoverinfo="skip",showlegend=False))
    # Decorative contour-like lines and a compass rose create a fantasy atlas mood.
    for k in range(5):
        xs=np.linspace(8,95,100)
        ys=50+ k*4 + 3*np.sin(xs/7+k*.7)
        fig.add_trace(go.Scatter(x=xs,y=ys,mode="lines",line=dict(color="rgba(211,183,133,0.12)",width=1),
                                 hoverinfo="skip",showlegend=False))
    # compass rose
    cx,cy=89,87
    for ang in np.arange(0,360,45):
        a=math.radians(float(ang))
        fig.add_trace(go.Scatter(x=[cx,cx+3*math.cos(a)],y=[cy,cy+3*math.sin(a)],
             mode="lines",line=dict(color="rgba(231,205,157,0.65)",width=1.3),hoverinfo="skip",showlegend=False))
    fig.add_annotation(x=cx,y=cy+4.2,text="N",showarrow=False,font=dict(size=10,color="#e6d0a5"))

def build_topology(hour_row=None, failed_edges=None, failed_substations=None):
    fig=go.Figure()
    failed_edges = set(failed_edges or [])
    failed_substations = set(failed_substations or [])
    _landscape(fig)
    pos={n:(v[0],v[1]) for n,v in NODES.items()}
    # Distributed assets connect to nearby substations; each source marker appears throughout the map.
    asset_names=[n for n,(_,_,k) in NODES.items() if k in ("solar","wind","battery","generator")]
    for n in asset_names:
        x,y,kind=NODES[n]
        source_class={"solar":"Solar","wind":"Wind","battery":"Battery","generator":"Main Generator"}[kind]
        for sub in _nearest_two_subs(x,y):
            sx,sy=SUB_POS[sub]
            col=COLORS[kind]
            failed=(source_class,sub) in failed_edges or sub in failed_substations
            fig.add_trace(go.Scatter(x=[x,sx],y=[y,sy],mode="lines",
                line=dict(color="#ff4d5e" if failed else col,width=2.4 if failed else 1.8,dash="dash" if failed else "dot"),
                opacity=.78 if failed else .43,hoverinfo="text",
                text=f"{n} → {sub}" + (" • FAILED" if failed else ""),showlegend=False))
    # Interconnected substation mesh: not a one-sided source-to-consumer diagram.
    mesh=[("S1","S2"),("S2","S3"),("S3","S4"),("S4","S5"),("S5","S6"),("S6","S7"),
          ("S7","S1"),("S1","S8"),("S2","S8"),("S3","S8"),("S4","S8"),("S5","S8"),
          ("S6","S8"),("S7","S8"),("S2","S6"),("S3","S5")]
    for u,v in mesh:
        x0,y0=pos[u]; x1,y1=pos[v]
        failed = (u,v) in failed_edges or (v,u) in failed_edges or u in failed_substations or v in failed_substations
        fig.add_trace(go.Scatter(x=[x0,x1],y=[y0,y1],mode="lines",
            line=dict(color="#ff4d5e" if failed else "rgba(209,218,226,0.66)",width=3.4 if failed else 2.8,dash="dash" if failed else "solid"),hoverinfo="text",
            text=f"{u} ↔ {v} • inter-substation corridor" + (" • FAILED" if failed else ""),showlegend=False))
    # Every consumer has two independent feeder routes to its two nearest substations.
    for n,(x,y,kind) in NODES.items():
        if kind not in ("consumer","critical"): continue
        for sub in _nearest_two_subs(x,y):
            sx,sy=SUB_POS[sub]
            failed=(sub,n) in failed_edges or sub in failed_substations
            fig.add_trace(go.Scatter(x=[x,sx],y=[y,sy],mode="lines",
                line=dict(color="#ff4d5e" if failed else "rgba(160,177,197,0.34)",width=2.2 if failed else 1.25,dash="dash" if failed else "solid"),
                hoverinfo="text",text=f"{sub} → {n}" + (" • FAILED" if failed else ""),showlegend=False))
    # Plot each node class, keep labels readable by labeling only substations and selected key assets.
    classes=[
      ("Solar sites","solar","solar"),
      ("Wind farms","wind","wind"),
      ("Battery banks","battery","battery"),
      ("Generator units","generator","generator"),
      ("Substations","substation","substation"),
      ("Critical consumers","critical","critical"),
      ("Consumers (50)","consumer","consumer")]
    for legend,kind,color_key in classes:
        names=[n for n,(_,_,k) in NODES.items() if k==kind]
        xs=[pos[n][0] for n in names]; ys=[pos[n][1] for n in names]
        sizes={"solar":14,"wind":14,"battery":16,"generator":17,"substation":27,"critical":12,"consumer":7}
        labels=[n if kind=="substation" else (n.replace(" ","<br>") if kind=="generator" else "") for n in names]
        custom=[]
        for n in names:
            x,y,k=NODES[n]
            if kind=="consumer" or kind=="critical":
                sub=_nearest_sub(x,y)
                custom.append(f"{n}<br>Type: {'Critical service' if kind=='critical' else 'Consumer'}<br>Nearest substation: {sub}<br>Individually modeled consumer with two independent feeder connections.")
            else:
                custom.append(f"{n}<br>Asset class: {kind.title()}<br>Nearest substation: {_nearest_sub(x,y)}<br>Illustrative location; source output is aggregated by class.")
        marker_colors=COLORS[color_key]
        if kind == "substation" and failed_substations:
            marker_colors=["#ff4d5e" if n in failed_substations else COLORS[color_key] for n in names]
        if kind in ("consumer","critical") and hour_row:
            marker_colors=[]
            for n in names:
                demand=float(hour_row.get(f"{n} demand (MW)",0.0))
                delivered=float(hour_row.get(f"{n} delivered (MW)",0.0))
                ratio=delivered/max(demand,1e-9)
                marker_colors.append("#52d6a2" if ratio >= .999 else ("#f2bf59" if ratio > .001 else "#ff4d5e"))
        fig.add_trace(go.Scatter(x=xs,y=ys,mode="markers+text" if kind=="substation" else "markers",
            text=labels,textposition="top center",textfont=dict(color="#f4e7cc",size=10),
            marker=dict(size=sizes[kind],color=marker_colors,
              line=dict(color="rgba(255,244,220,0.9)",width=1.6),
              opacity=.97),
            name=legend,customdata=custom,
            hovertemplate="<b>%{customdata}</b><extra></extra>"))
    # Map title and map labels.
    for x,y,label in [(16,92,"THE WESTERN REACH"),(51,96,"THE HIGHLANDS"),(83,61,"EASTERN MARCH"),
                      (17,12,"SOUTHERN COAST"),(71,13,"THE OLD ROAD")]:
        fig.add_annotation(x=x,y=y,text=label,showarrow=False,
            font=dict(size=8,color="rgba(237,216,176,0.65)"))
    fig.update_layout(
        height=900,margin=dict(l=8,r=8,t=42,b=8),
        paper_bgcolor="#17232b",plot_bgcolor="#17232b",
        font=dict(family="Georgia, serif",size=10,color="#e9dec9"),
        title=dict(text="THE GRIDLANDS  •  DISTRIBUTED POWER ATLAS",x=.02,
                   font=dict(family="Georgia, serif",size=16,color="#f2dfb5")),
        showlegend=True,
        legend=dict(orientation="h",y=1.035,x=0,font=dict(size=10,color="#e9dec9"),
                    bgcolor="rgba(23,35,43,.85)"),
        xaxis=dict(visible=False,range=[0,100],fixedrange=True),
        yaxis=dict(visible=False,range=[0,100],fixedrange=True,scaleanchor="x",scaleratio=1),
        hovermode="closest",
    )
    return fig
