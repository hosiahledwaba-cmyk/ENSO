"""Integration tests for anticipatory preparedness and early-action workflow APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_preparedness_matrix_endpoint(client: TestClient) -> None:
    """Verify trigger matrix returns operational context, trigger tiers, and sector actions."""
    res = client.get("/api/v1/preparedness/matrix")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "operational"
    ctx = data["operational_context"]
    assert ctx["active_risk_tier"] == "HIGH"
    assert ctx["forecast_probability_pct"] == 42.8
    assert ctx["climatological_base_rate_pct"] == 20.0

    # Verify 4 trigger tiers
    tiers = data["trigger_tiers"]
    assert len(tiers) == 4
    tier_names = [t["tier"] for t in tiers]
    assert "NORMAL" in tier_names
    assert "ELEVATED" in tier_names
    assert "HIGH" in tier_names
    assert "CRITICAL" in tier_names

    # Verify actions list
    actions = data["actions"]
    assert len(actions) >= 5
    summary = data["actions_summary"]
    assert summary["total_actions"] == len(actions)
    assert summary["triggered"] >= 1


def test_list_preparedness_actions_with_filters(client: TestClient) -> None:
    """Verify filtering actions by sector, tier, and status."""
    # Sector filter
    res = client.get("/api/v1/preparedness/actions?sector=AGRICULTURE")
    assert res.status_code == 200
    data = res.json()
    assert all(a["sector"] == "AGRICULTURE" for a in data["actions"])
    assert len(data["actions"]) >= 2

    # Tier filter
    res_tier = client.get("/api/v1/preparedness/actions?tier=HIGH")
    assert res_tier.status_code == 200
    data_tier = res_tier.json()
    assert all(a["tier"] == "HIGH" for a in data_tier["actions"])


def test_trigger_preparedness_action(client: TestClient) -> None:
    """Verify executing and transitioning an anticipatory preparedness action."""
    action_id = "ACT_AGRI_01"
    payload = {
        "action_id": action_id,
        "status": "EXECUTED",
        "operator_name": "Senior Agro-Climatologist",
        "notes": "Field distribution protocol verified; 500 vouchers issued.",
    }
    res = client.post(f"/api/v1/preparedness/actions/{action_id}/trigger", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["action"]["status"] == "EXECUTED"
    assert "Senior Agro-Climatologist" in data["action"]["operator_notes"]

    # Verify 404 for unknown action
    res_404 = client.post("/api/v1/preparedness/actions/NON_EXISTENT_99/trigger", json=payload)
    assert res_404.status_code == 404

    # Verify 400 for invalid status
    bad_payload = {"action_id": action_id, "status": "INVALID_STATE"}
    res_400 = client.post(f"/api/v1/preparedness/actions/{action_id}/trigger", json=bad_payload)
    assert res_400.status_code == 400
