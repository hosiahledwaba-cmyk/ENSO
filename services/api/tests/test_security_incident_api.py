"""Integration tests for security incident centre and trust telemetry APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_security_incidents_list(client: TestClient) -> None:
    """Verify security incident feed returns curated and live operational incidents."""
    res = client.get("/api/v1/security/incidents")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "operational"
    assert "incidents" in data
    assert len(data["incidents"]) >= 5

    # Check for both operational and simulated incident classifications
    classifications = {i["epistemic_classification"] for i in data["incidents"]}
    assert "OPERATIONAL_TELEMETRY" in classifications
    assert "SIMULATED_EXPERIMENT" in classifications

    # Check that simulations are explicitly marked with disclaimers
    sim_incidents = [
        i for i in data["incidents"] if i["epistemic_classification"] == "SIMULATED_EXPERIMENT"
    ]
    assert len(sim_incidents) >= 2
    for sim in sim_incidents:
        assert "SIMULATION" in sim["subsystem"] or "SIMULATED" in sim["epistemic_classification"]
        assert "epistemic_boundary" in sim["technical_details"]


def test_security_incidents_filtering(client: TestClient) -> None:
    """Verify filtering incidents by severity, subsystem, and classification."""
    # Filter by subsystem
    res_sub = client.get("/api/v1/security/incidents?subsystem=DEFENSE_SCREENING")
    assert res_sub.status_code == 200
    data_sub = res_sub.json()
    assert all(i["subsystem"] == "DEFENSE_SCREENING" for i in data_sub["incidents"])
    assert len(data_sub["incidents"]) >= 2

    # Filter by severity
    res_sev = client.get("/api/v1/security/incidents?severity=WARNING")
    assert res_sev.status_code == 200
    data_sev = res_sev.json()
    assert all(i["severity"] == "WARNING" for i in data_sev["incidents"])

    # Filter by classification
    res_sim = client.get("/api/v1/security/incidents?classification=SIMULATED_EXPERIMENT")
    assert res_sim.status_code == 200
    data_sim = res_sim.json()
    assert all(
        i["epistemic_classification"] == "SIMULATED_EXPERIMENT" for i in data_sim["incidents"]
    )


def test_security_summary_endpoint(client: TestClient) -> None:
    """Verify cyber-resilience summary, trust index, and subsystem gates."""
    res = client.get("/api/v1/security/summary")
    assert res.status_code == 200
    data = res.json()

    assert data["overall_posture"] in {"HEALTHY", "DEGRADED", "COMPROMISED"}
    assert 0 <= data["data_trust_index"] <= 100
    assert "subsystem_gates" in data
    assert len(data["subsystem_gates"]) >= 4

    gate_subsystems = [g["subsystem"] for g in data["subsystem_gates"]]
    assert "Model Artefacts" in gate_subsystems
    assert "Data Provenance" in gate_subsystems
    assert "Defensive Ingestion Screening" in gate_subsystems
    assert "Training Poisoning Resilience" in gate_subsystems

    # Verify epistemic rules
    assert "epistemic_rules_enforced" in data
    assert len(data["epistemic_rules_enforced"]) >= 4
