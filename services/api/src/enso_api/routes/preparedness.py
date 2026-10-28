"""Anticipatory drought preparedness and early-action workflow router."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from enso_api.db import (
    PERMITTED_TRANSITIONS,
    VALID_ACTION_STATUSES,
    PreparednessActionNotFoundError,
    PreparednessTransitionError,
    db_get_preparedness_actions,
    db_get_preparedness_audit_log,
    db_update_preparedness_action_state,
    get_pool,
)

logger = logging.getLogger("enso_api.preparedness")

router = APIRouter(prefix="/api/v1/preparedness", tags=["Anticipatory Action & Preparedness"])


class TriggerActionRequest(BaseModel):
    action_id: str | None = Field(
        default=None,
        description="Optional action identifier to trigger or update (defaults to path parameter).",
    )
    status: str = Field(
        default="EXECUTED",
        description="Target status: 'MONITORING', 'READY', 'TRIGGERED', 'EXECUTED'.",
    )
    operator_name: str = Field(
        default="Operational Agro-Meteorologist",
        description="Name or callsign of operating official.",
    )
    notes: str = Field(
        default="Anticipatory action execution confirmed based on verified November 1st seasonal outlook.",
        description="Operational context or field deployment notes.",
    )


class PreparednessAction(BaseModel):
    id: str
    tier: str
    tier_label: str
    threshold_min_pct: float
    threshold_max_pct: float
    sector: str
    action_name: str
    description: str
    lead_agency: str
    target_subregions: list[str]
    lead_time_days: int
    status: str
    last_updated_at: str
    operator_notes: str | None = None


# In-memory operational action registry (initialized with standardized anticipatory actions)
_DEFAULT_ACTIONS: list[dict[str, Any]] = [
    {
        "id": "ACT_AGRI_01",
        "tier": "ELEVATED",
        "tier_label": "Elevated Risk (25% - 40%)",
        "threshold_min_pct": 25.0,
        "threshold_max_pct": 40.0,
        "sector": "AGRICULTURE",
        "action_name": "Agro-Ecological Advisory & Soil Moisture Conservation Alert",
        "description": "Issue early advisory to agricultural extension officers across Limpopo and Western Maize belt promoting minimum tillage, mulching, and delayed dry planting.",
        "lead_agency": "DALRRD Agricultural Extension Directorate",
        "target_subregions": ["ZA_LIMPOPO", "ZA_MAIZE_WEST"],
        "lead_time_days": 14,
        "status": "TRIGGERED",
        "last_updated_at": "2026-10-28T02:00:00Z",
        "operator_notes": "Alert dispatched to district extension hubs ahead of November planting window.",
    },
    {
        "id": "ACT_AGRI_02",
        "tier": "HIGH",
        "tier_label": "High Risk (40% - 60%)",
        "threshold_min_pct": 40.0,
        "threshold_max_pct": 60.0,
        "sector": "AGRICULTURE",
        "action_name": "Drought-Tolerant Sorghum & Millet Seed Voucher Distribution",
        "description": "Trigger anticipatory voucher distribution for short-season, drought-tolerant grain varieties (sorghum, cowpeas, pearl millet) to replace water-intensive maize.",
        "lead_agency": "South African Grain Information Service (SAGIS) & Agricultural Research Council (ARC)",
        "target_subregions": ["ZA_LIMPOPO", "ZA_MAIZE_WEST"],
        "lead_time_days": 21,
        "status": "TRIGGERED",
        "last_updated_at": "2026-10-28T02:30:00Z",
        "operator_notes": "Triggered by operational model forecast exceeding 40% threshold (42.8% estimated).",
    },
    {
        "id": "ACT_WATER_01",
        "tier": "ELEVATED",
        "tier_label": "Elevated Risk (25% - 40%)",
        "threshold_min_pct": 25.0,
        "threshold_max_pct": 40.0,
        "sector": "WATER_RESOURCES",
        "action_name": "Limpopo & Olifants Catchment Storage Audit & Loss Prevention",
        "description": "Conduct structural audit of major irrigation canals and municipal bulk pipelines; inspect community boreholes and groundwater extraction sensors.",
        "lead_agency": "Department of Water and Sanitation (DWS) & Limpopo Catchment Agency",
        "target_subregions": ["ZA_LIMPOPO", "ZA_SRZ"],
        "lead_time_days": 30,
        "status": "READY",
        "last_updated_at": "2026-10-27T18:00:00Z",
        "operator_notes": "Maintenance teams on standby.",
    },
    {
        "id": "ACT_WATER_02",
        "tier": "HIGH",
        "tier_label": "High Risk (40% - 60%)",
        "threshold_min_pct": 40.0,
        "threshold_max_pct": 60.0,
        "sector": "WATER_RESOURCES",
        "action_name": "Anticipatory Irrigation Scheme Water Quota Adjustments",
        "description": "Gazette voluntary 15% reduction in commercial irrigation abstractions; reserve upstream dam capacity for livestock and essential domestic potable supplies.",
        "lead_agency": "Catchment Management Agencies (Limpopo & Inkomati-Usuthu)",
        "target_subregions": ["ZA_LIMPOPO", "ZA_MAIZE_WEST"],
        "lead_time_days": 15,
        "status": "TRIGGERED",
        "last_updated_at": "2026-10-28T02:45:00Z",
        "operator_notes": "Advisory sent to Irrigation Boards for December implementation.",
    },
    {
        "id": "ACT_LIVESTOCK_01",
        "tier": "HIGH",
        "tier_label": "High Risk (40% - 60%)",
        "threshold_min_pct": 40.0,
        "threshold_max_pct": 60.0,
        "sector": "LIVESTOCK",
        "action_name": "Pastoral Fodder Banking & Destocking Assistance Setup",
        "description": "Establish community fodder storage depots in communal grazing areas; register commercial abattoir transport subsidies for proactive herd destocking.",
        "lead_agency": "National Agricultural Marketing Council (NAMC) & Red Meat Producers Organisation",
        "target_subregions": ["ZA_LIMPOPO", "ZA_MAIZE_WEST"],
        "lead_time_days": 25,
        "status": "TRIGGERED",
        "last_updated_at": "2026-10-28T03:00:00Z",
        "operator_notes": "Feed reserves mobilized in Vhembe and Capricorn districts.",
    },
    {
        "id": "ACT_DISASTER_01",
        "tier": "HIGH",
        "tier_label": "High Risk (40% - 60%)",
        "threshold_min_pct": 40.0,
        "threshold_max_pct": 60.0,
        "sector": "DISASTER_RELIEF",
        "action_name": "Anticipatory Action Contingency Fund Release Notice",
        "description": "Notify Provincial Disaster Management Centres (PDMCs) in Limpopo, Free State, and North West to unlock anticipatory resilience financing ahead of peak summer deficit.",
        "lead_agency": "National Disaster Management Centre (NDMC)",
        "target_subregions": ["ZA_SRZ", "ZA_LIMPOPO", "ZA_MAIZE_WEST", "ZA_MAIZE_EAST"],
        "lead_time_days": 10,
        "status": "READY",
        "last_updated_at": "2026-10-28T01:15:00Z",
        "operator_notes": "Contingency allocation staged for release upon SADC SARCOF confirmation.",
    },
    {
        "id": "ACT_DISASTER_02",
        "tier": "CRITICAL",
        "tier_label": "Critical Risk (> 60%)",
        "threshold_min_pct": 60.0,
        "threshold_max_pct": 100.0,
        "sector": "DISASTER_RELIEF",
        "action_name": "Emergency Food Security Safety Net & Bulk Water Trucking Mobilization",
        "description": "Deploy emergency social grant top-ups for subsistence farming households; preposition high-capacity mobile water tankers in rural municipal wards.",
        "lead_agency": "Department of Social Development & South African National Defence Force (SANDF)",
        "target_subregions": ["ZA_LIMPOPO", "ZA_MAIZE_WEST"],
        "lead_time_days": 7,
        "status": "MONITORING",
        "last_updated_at": "2026-10-27T12:00:00Z",
        "operator_notes": "On standby. Requires regional forecast probability >= 60%.",
    },
]

# Fallback in-memory operational action registry (used when database is offline)
_ACTIONS_DB: list[dict[str, Any]] = [dict(a) for a in _DEFAULT_ACTIONS]


async def _get_current_actions() -> list[dict[str, Any]]:
    """Retrieve current actions from PostgreSQL if connected, falling back to memory store."""
    pool = get_pool()
    if pool is not None:
        db_actions = await db_get_preparedness_actions()
        if db_actions:
            return db_actions
    return _ACTIONS_DB


@router.get("/matrix")
async def get_preparedness_matrix() -> dict[str, Any]:
    """Retrieve full Anticipatory Action Trigger Matrix with persisted operational status."""
    actions = await _get_current_actions()

    # Current active operational drought probability from baseline model (42.8%)
    operational_prob_pct = 42.8
    current_tier = "HIGH"

    # Count actions by status
    triggered_count = sum(1 for a in actions if a["status"] == "TRIGGERED")
    executed_count = sum(1 for a in actions if a["status"] == "EXECUTED")
    ready_count = sum(1 for a in actions if a["status"] == "READY")
    monitoring_count = sum(1 for a in actions if a["status"] == "MONITORING")

    return {
        "status": "operational",
        "operational_context": {
            "issue_date": "2026-11-01",
            "convective_season": "DJF 2026/27",
            "forecast_probability_pct": operational_prob_pct,
            "active_risk_tier": current_tier,
            "active_risk_label": "High Severe Drought Risk (40% - 60%)",
            "climatological_base_rate_pct": 20.0,
            "risk_ratio": 2.14,
            "decision_rule": (
                "Under Anticipatory Action Protocol §6, when operational model probability exceeds 40%, "
                "High Risk Agricultural and Water Resource triggers are automatically activated."
            ),
        },
        "trigger_tiers": [
            {
                "tier": "NORMAL",
                "label": "Baseline / Normal Risk",
                "range": "< 25%",
                "status": "CLEARED",
                "description": "Routine seasonal monitoring and baseline water resource stewardship.",
            },
            {
                "tier": "ELEVATED",
                "label": "Elevated Risk",
                "range": "25% - 40%",
                "status": "ACTIVE_SURPASS",
                "description": "Advisory alerts to agricultural extension networks and soil moisture conservation.",
            },
            {
                "tier": "HIGH",
                "label": "High Severe Drought Risk",
                "range": "40% - 60%",
                "status": "CURRENTLY_TRIGGERED",
                "description": "Anticipatory action execution: drought-tolerant seeds, irrigation rationing, fodder banking.",
            },
            {
                "tier": "CRITICAL",
                "label": "Critical Emergency Drought Risk",
                "range": ">= 60%",
                "status": "STANDBY",
                "description": "Emergency humanitarian mitigation, social cash transfers, and emergency water trucking.",
            },
        ],
        "actions_summary": {
            "total_actions": len(actions),
            "triggered": triggered_count,
            "executed": executed_count,
            "ready": ready_count,
            "monitoring": monitoring_count,
        },
        "actions": actions,
    }


@router.get("/actions")
async def list_preparedness_actions(
    tier: str | None = None,
    sector: str | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List anticipatory preparedness actions from persisted store with optional filtering."""
    results = await _get_current_actions()
    if tier:
        results = [a for a in results if a["tier"].upper() == tier.upper()]
    if sector:
        results = [a for a in results if a["sector"].upper() == sector.upper()]
    if status_filter:
        results = [a for a in results if a["status"].upper() == status_filter.upper()]

    return {
        "status": "success",
        "actions": results,
        "count": len(results),
    }


@router.post("/actions/{action_id}/trigger")
async def trigger_action(action_id: str, payload: TriggerActionRequest) -> dict[str, Any]:
    """Execute, escalate, or update the operational status of an anticipatory preparedness action.

    Status updates are persisted to PostgreSQL and recorded in an immutable audit log.
    The execution reflects a recorded operational workflow state; external delivery or field
    completion is tracked separately through physical monitoring channels.
    """
    target_status = payload.status.upper()
    if target_status not in VALID_ACTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Allowed: {sorted(VALID_ACTION_STATUSES)}",
        )

    # 1. Primary path: PostgreSQL persistence with row-level transaction lock
    pool = get_pool()
    if pool is not None:
        try:
            updated_action = await db_update_preparedness_action_state(
                action_id=action_id,
                target_status=target_status,
                operator_name=payload.operator_name,
                notes=payload.notes,
                dispatch_type="RECORDED_WORKFLOW_STATE",
                is_simulated=False,
            )
            logger.info("Preparedness action %s persisted with status %s", action_id, target_status)
            return {
                "status": "updated",
                "persistence": "postgresql_persisted",
                "dispatch_type": "RECORDED_WORKFLOW_STATE",
                "action": updated_action,
                "message": (
                    f"Action {action_id} successfully transitioned to {target_status} "
                    f"(Recorded Workflow State in PostgreSQL)."
                ),
            }
        except PreparednessActionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except PreparednessTransitionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to persist preparedness action %s: %s", action_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist preparedness action state: {exc}",
            ) from exc

    # 2. In-memory fallback (used only when database is disabled/offline)
    for item in _ACTIONS_DB:
        if item["id"] == action_id or item["id"].lower() == action_id.lower():
            current_status = item["status"]
            allowed = PERMITTED_TRANSITIONS.get(current_status, VALID_ACTION_STATUSES)
            if target_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Illegal transition from '{current_status}' to '{target_status}'. "
                        f"Permitted next states: {sorted(allowed)}"
                    ),
                )

            item["status"] = target_status
            item["last_updated_at"] = datetime.now(UTC).isoformat()
            item["operator_notes"] = f"[{payload.operator_name}] {payload.notes}"

            logger.info("Preparedness action %s updated in memory to %s", action_id, target_status)
            return {
                "status": "updated",
                "persistence": "in_memory_fallback",
                "dispatch_type": "RECORDED_WORKFLOW_STATE",
                "action": item,
                "message": f"Action {action_id} transitioned to {target_status} (memory fallback).",
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Preparedness action '{action_id}' not found in registry.",
    )


@router.get("/actions/{action_id}/audit")
async def get_action_audit_log(action_id: str, limit: int = 50) -> dict[str, Any]:
    """Retrieve historical state transitions and operator audit log for a specific action."""
    entries = await db_get_preparedness_audit_log(action_id=action_id, limit=limit)
    return {
        "status": "success",
        "action_id": action_id,
        "count": len(entries),
        "audit_trail": entries,
    }
