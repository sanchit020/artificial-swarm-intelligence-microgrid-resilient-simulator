import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.microgrid import Settings, simulate


def test_agent_messages_logged_in_swarm_mode():
    s = Settings(seed=2026, population=8, generations=1, dispatch_mode="swarm")
    res = simulate([0] * 24, s, seed=2026, line_capacity_overrides={("S3", "S5"): 0.0, ("S5", "S3"): 0.0})
    msgs = res.get("agent_messages")
    assert msgs is not None
    assert len(msgs) > 0
    assert "Sender" in msgs.columns
    assert "Receiver" in msgs.columns
    assert "Type" in msgs.columns
    assert any(msgs["Type"].isin(["REQUEST_POWER", "OFFER_POWER", "LINE_TRIPPED", "SHED_ALERT"]))


def test_decentralized_agents_respond_to_line_cut():
    s = Settings(seed=2026, population=8, generations=1, dispatch_mode="swarm")
    # Severe N-2 cut
    res = simulate([0] * 24, s, seed=2026,
                   line_capacity_overrides={("S3", "S5"): 0.0, ("S5", "S3"): 0.0, ("S2", "S8"): 0.0, ("S8", "S2"): 0.0})
    msgs = res["agent_messages"]
    tripped_alerts = msgs[msgs["Type"] == "LINE_TRIPPED"]
    assert len(tripped_alerts) > 0

