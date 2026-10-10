from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import (
    Zone, ZoneRule, Actuator, SensorTelemetry, Alert, AlertSeverity, AlertType, FertigationLog, TriggerType
)
from app.schemas.domain import TelemetryCreate, TelemetryResponse
from app.services.rule_engine import ClassicalRuleEngine
from app.services.et0_calculator import BananaET0Calculator
from app.services.telemetry_sim import simulator_instance

router = APIRouter(prefix="/telemetry", tags=["Sensor Telemetry"])

# In-memory subscriber list for live WebSockets (will be linked in main.py)
active_telemetry_cache: Dict[str, Any] = {}

@router.post("/", response_model=Dict[str, Any])
async def ingest_telemetry(payload: TelemetryCreate, db: AsyncSession = Depends(get_db)):
    """
    Ingest sensor telemetry from ESP32 (Modbus RS485 7-in-1 + SHT30 + BH1750)
    or from the Hardware Simulator.
    Runs Mode 1 Classical Rule-Based Engine automatically.
    """
    # 1. Fetch Zone and its Rule
    zone_res = await db.execute(select(Zone).where(Zone.id == payload.zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    rule_res = await db.execute(select(ZoneRule).where(ZoneRule.zone_id == zone.id))
    rule = rule_res.scalar_one_or_none()
    if not rule:
        # Default safety rule if not configured yet
        rule = ZoneRule(
            id=str(uuid.uuid4()),
            tenant_id=zone.tenant_id,
            zone_id=zone.id,
            moisture_trigger_min_pct=70.0,
            moisture_cutoff_max_pct=80.0,
            max_safe_ec_ds_m=0.85,
            ec_hard_cutoff_ds_m=1.00,
            wind_cutoff_kmh=30.0,
            target_k_ppm=250.0
        )
        db.add(rule)
        await db.flush()

    actuators_res = await db.execute(select(Actuator).where(Actuator.zone_id == zone.id))
    actuators = actuators_res.scalars().all()

    # 2. Record Telemetry
    telemetry = SensorTelemetry(
        id=str(uuid.uuid4()),
        time=payload.time or datetime.now(timezone.utc),
        tenant_id=payload.tenant_id,
        zone_id=payload.zone_id,
        device_id=payload.device_id,
        soil_moisture_pct=payload.soil_moisture_pct,
        soil_temp_c=payload.soil_temp_c,
        soil_ec_ds_m=payload.soil_ec_ds_m,
        soil_ph=payload.soil_ph,
        soil_n_mg_kg=payload.soil_n_mg_kg,
        soil_p_mg_kg=payload.soil_p_mg_kg,
        soil_k_mg_kg=payload.soil_k_mg_kg,
        air_temp_c=payload.air_temp_c,
        air_rh_pct=payload.air_rh_pct,
        light_lux=payload.light_lux,
        solar_radiation_w_m2=payload.solar_radiation_w_m2,
        wind_speed_kmh=payload.wind_speed_kmh,
        rain_rate_mm_h=payload.rain_rate_mm_h,
        battery_voltage=payload.battery_voltage,
        wifi_rssi_dbm=payload.wifi_rssi_dbm
    )
    db.add(telemetry)

    # 3. Evaluate Rule-Based Engine (Mode 1)
    eval_result = ClassicalRuleEngine.evaluate(zone, rule, telemetry, actuators)

    # 4. Save any triggered Alerts
    created_alerts = []
    for al in eval_result.alerts:
        alert = Alert(
            id=str(uuid.uuid4()),
            tenant_id=zone.tenant_id,
            farm_id=zone.farm_id,
            zone_id=zone.id,
            severity=al["severity"],
            alert_type=al["alert_type"],
            title=al["title"],
            message=al["message"],
            suggested_action=al.get("suggested_action"),
            line_notified=False,
            is_resolved=False
        )
        db.add(alert)
        created_alerts.append(al)

    # 5. Apply Actuator state changes if commanded
    executed_actions = []
    for act_cmd in eval_result.actions:
        for act in actuators:
            if act.id == act_cmd["actuator_id"]:
                act.is_active = (act_cmd["command"] == "START")
                executed_actions.append(act_cmd)
                
                # Log execution
                log = FertigationLog(
                    id=str(uuid.uuid4()),
                    time=datetime.now(timezone.utc),
                    tenant_id=zone.tenant_id,
                    zone_id=zone.id,
                    device_id=payload.device_id,
                    actuator_id=act.id,
                    trigger_type=TriggerType.RULE_THRESHOLD.value,
                    growth_stage=zone.current_stage,
                    action_type="IRRIGATION_ONLY" if act.actuator_type == "VALVE_IRRIGATION" else "FERTIGATION_K",
                    duration_seconds=act_cmd.get("duration_seconds", 600),
                    pre_soil_moisture=payload.soil_moisture_pct,
                    pre_soil_ec=payload.soil_ec_ds_m,
                    notes=act_cmd.get("reason")
                )
                db.add(log)

    await db.commit()

    # Update cache
    active_telemetry_cache[zone.id] = payload.model_dump()

    return {
        "status": "success",
        "telemetry_id": telemetry.id,
        "actions_taken": executed_actions,
        "alerts_triggered": created_alerts,
        "engine_logs": eval_result.logs
    }

@router.get("/latest/{zone_id}")
async def get_latest_telemetry(zone_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get latest telemetry reading for a zone with Penman-Monteith ET0 calculation
    """
    zone_res = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    result = await db.execute(
        select(SensorTelemetry)
        .where(SensorTelemetry.zone_id == zone_id)
        .order_by(SensorTelemetry.time.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if not latest:
        # If no real data yet, return simulated initial reading
        sim_data = simulator_instance.step()
        return {
            "source": "SIMULATED_INITIAL",
            "zone_id": zone_id,
            "stage": zone.current_stage,
            "data": sim_data
        }

    # Calculate ET0 & water requirement
    water_req = BananaET0Calculator.calculate_daily_irrigation(
        growth_stage=zone.current_stage,
        temp_c=latest.air_temp_c or 30.0,
        rh_pct=latest.air_rh_pct or 70.0,
        wind_kmh=latest.wind_speed_kmh or 10.0,
        solar_rad_w_m2=latest.solar_radiation_w_m2 or 500.0,
        emitter_flow_rate_lph=zone.emitter_flow_rate_lph
    )

    return {
        "source": "DATABASE",
        "zone_id": zone.id,
        "zone_name": zone.name,
        "stage": zone.current_stage,
        "time": latest.time.isoformat(),
        "soil": {
            "moisture_pct": latest.soil_moisture_pct,
            "temp_c": latest.soil_temp_c,
            "ec_ds_m": latest.soil_ec_ds_m,
            "ph": latest.soil_ph,
            "n_ppm": latest.soil_n_mg_kg,
            "p_ppm": latest.soil_p_mg_kg,
            "k_ppm": latest.soil_k_mg_kg
        },
        "weather": {
            "temp_c": latest.air_temp_c,
            "rh_pct": latest.air_rh_pct,
            "lux": latest.light_lux,
            "solar_radiation_w_m2": latest.solar_radiation_w_m2,
            "wind_speed_kmh": latest.wind_speed_kmh,
            "rain_rate_mm_h": latest.rain_rate_mm_h
        },
        "et0_recommendation": water_req
    }

@router.post("/simulate-step/{zone_id}")
async def trigger_simulation_step(
    zone_id: str,
    scenario: Optional[str] = Query(None, description="NORMAL, HIGH_WIND, HIGH_SALINITY, DROUGHT_STRESS"),
    db: AsyncSession = Depends(get_db)
):
    """
    Step the Hardware Simulator and ingest through the live pipeline!
    Allows interactive testing of alerts, rule engine, and graphs.
    """
    zone_res = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = zone_res.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Check actuator active status
    actuators_res = await db.execute(select(Actuator).where(Actuator.zone_id == zone.id))
    actuators = actuators_res.scalars().all()
    valve_active = any(a.is_active for a in actuators if a.actuator_type == "VALVE_IRRIGATION")
    dosing_active = any(a.is_active for a in actuators if "FERTILIZER" in a.actuator_type)

    sim_reading = simulator_instance.step(
        irrigation_active=valve_active,
        dosing_k_active=dosing_active,
        scenario=scenario
    )

    # Ingest through standard pipeline
    payload = TelemetryCreate(
        tenant_id=zone.tenant_id,
        zone_id=zone.id,
        device_id="ESP32-S3-SIMULATOR-001",
        **sim_reading
    )

    return await ingest_telemetry(payload, db)
