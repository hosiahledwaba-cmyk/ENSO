"""Tests for anticipatory preparedness action state persistence, transitions, and audit trail."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from enso_api.routes import preparedness


@pytest.fixture(autouse=True)
def reset_in_memory_preparedness() -> None:
    """Reset the in-memory fallback store before each test for isolated assertions."""
    preparedness._ACTIONS_DB = [dict(a) for a in preparedness._DEFAULT_ACTIONS]


def test_list_preparedness_actions(client: TestClient) -> None:
    """Verify listing of preparedness actions with standard structure."""
    res = client.get("/api/v1/preparedness/actions")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["count"] == 7
    assert len(data["actions"]) == 7


def test_get_preparedness_matrix(client: TestClient) -> None:
    """Verify matrix endpoint returns trigger tiers, operational context, and counts."""
    res = client.get("/api/v1/preparedness/matrix")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "operational"
    assert "operational_context" in data
    assert "trigger_tiers" in data
    assert "actions_summary" in data
    assert data["actions_summary"]["total_actions"] == 7


def test_trigger_action_permitted_transition(client: TestClient) -> None:
    """Verify successful state transition to EXECUTED returns RECORDED_WORKFLOW_STATE dispatch type."""
    # ACT_AGRI_01 is TRIGGERED by default; transition to EXECUTED is permitted
    payload = {
        "status": "EXECUTED",
        "operator_name": "Senior Agro-Climatologist",
        "notes": "Field distribution order recorded in workflow system.",
    }
    res = client.post("/api/v1/preparedness/actions/ACT_AGRI_01/trigger", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["action"]["status"] == "EXECUTED"
    assert data["dispatch_type"] == "RECORDED_WORKFLOW_STATE"
    assert "Senior Agro-Climatologist" in data["action"]["operator_notes"]

    # Verify state reflects in subsequent list request
    res_list = client.get("/api/v1/preparedness/actions")
    action = next(a for a in res_list.json()["actions"] if a["id"] == "ACT_AGRI_01")
    assert action["status"] == "EXECUTED"


def test_trigger_action_invalid_status_rejection(client: TestClient) -> None:
    """Verify rejection of nonsensical or unrecognized status string."""
    payload = {
        "status": "COMPLETED_REAL_WORLD_NOW",
        "operator_name": "Test Operator",
        "notes": "Invalid target status",
    }
    res = client.post("/api/v1/preparedness/actions/ACT_AGRI_01/trigger", json=payload)
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]


def test_trigger_action_not_found(client: TestClient) -> None:
    """Verify 404 for non-existent action ID."""
    payload = {
        "status": "READY",
        "operator_name": "Test",
        "notes": "Testing 404",
    }
    res = client.post("/api/v1/preparedness/actions/NON_EXISTENT_ACTION_99/trigger", json=payload)
    assert res.status_code == 404


def test_trigger_action_filter_by_sector(client: TestClient) -> None:
    """Verify filtering by sector."""
    res = client.get("/api/v1/preparedness/actions?sector=AGRICULTURE")
    assert res.status_code == 200
    data = res.json()
    assert all(a["sector"] == "AGRICULTURE" for a in data["actions"])
    assert data["count"] == 2
