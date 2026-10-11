from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Zone, Actuator, Alert, SensorTelemetry, FertigationLog, TriggerType, Device
from app.services.et0_calculator import BananaET0Calculator
from app.services.telemetry_sim import simulator_instance

router = APIRouter(prefix="/mobile", tags=["Farmer Mobile App & LINE LIFF"])

# In-memory settings for zone runtimes and automation mode
zone_automation_settings = {
    "mode": "AI_ASSISTED",  # or "TIMER_ONLY"
    "zone_1_runtime_mins": 15,
    "zone_2_runtime_mins": 20,
    "zone_3_runtime_mins": 15,
    "zone_4_runtime_mins": 15,
    "notify_wind_enabled": True,
    "notify_salinity_enabled": True,
    "line_user_id": "U1234567890abcdef"
}

@router.get("/summary")
async def get_farmer_mobile_summary(
    zone_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    High-speed mobile summary for LINE LIFF Digital Twin.
    Contains LCD 2004 4-line state, 3 power rail voltages, 2 pumps, and 4 zones.
    """
    if zone_id:
        zone_res = await db.execute(select(Zone).where(Zone.id == zone_id))
    else:
        zone_res = await db.execute(select(Zone).limit(1))
    
    zone = zone_res.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="No planting zone found")

    # Fetch latest telemetry
    latest_res = await db.execute(
        select(SensorTelemetry)
        .where(SensorTelemetry.zone_id == zone.id)
        .order_by(SensorTelemetry.time.desc())
        .limit(1)
    )
    latest = latest_res.scalar_one_or_none()

    if latest:
        moisture = round(latest.soil_moisture_pct or 0.0, 1)
        soil_temp = round(latest.soil_temp_c or 28.5, 1)
        ec = round(latest.soil_ec_ds_m or 0.0, 3)
        k = round(latest.soil_k_mg_kg or 265.0, 0)
        ph = round(latest.soil_ph or 6.5, 1)
        temp = round(latest.air_temp_c or 27.9, 1)
        rh = round(latest.air_rh_pct or 48.0, 0)
        lux = round(latest.light_lux or 0.0, 0)
        wind = round(latest.wind_speed_kmh or 8.5, 1)
    else:
        sim = simulator_instance.step()
        moisture = sim["soil_moisture_pct"]
        ec = sim["soil_ec_ds_m"]
        k = sim["soil_k_mg_kg"]
        ph = sim["soil_ph"]
        temp = sim["air_temp_c"]
        rh = sim["air_rh_pct"]
        lux = sim.get("light_lux", 0.0)
        wind = sim["wind_speed_kmh"]

    # Actuators
    actuators_res = await db.execute(select(Actuator).where(Actuator.zone_id == zone.id))
    actuators = actuators_res.scalars().all()

    pump_water = next((a for a in actuators if a.actuator_type == "MAIN_PUMP"), None)
    pump_fert = next((a for a in actuators if "FERTILIZER" in a.actuator_type), None)
    valves = [a for a in actuators if a.actuator_type == "VALVE_IRRIGATION"]

    # Format 4 zones
    def get_zone_state(idx):
        if idx < len(valves):
            return {"id": valves[idx].id, "name": f"โซน {idx+1}", "is_active": valves[idx].is_active}
        return {"id": f"dummy-z{idx+1}", "name": f"โซน {idx+1}", "is_active": False}

    z1 = get_zone_state(0)
    z2 = get_zone_state(1)
    z3 = get_zone_state(2)
    z4 = get_zone_state(3)

    # Active running string for LCD line 4
    active_zones_str = "".join([str(i+1) for i, z in enumerate([z1, z2, z3, z4]) if z["is_active"]]) or "NONE"
    pump_str = "ON" if (pump_water and pump_water.is_active) else "OFF"
    fert_str = "ON" if (pump_fert and pump_fert.is_active) else "OFF"

    # Virtual LCD 2004 4-line content with Real Light Lux & Weather!
    lcd_lines = [
        f"T:{temp:4.1f}C RH:{rh:2.0f}% L:{lux:4.0f}",
        f"Soil:{moisture:4.1f}% pH:{ph:3.1f}",
        f"EC:{ec:4.2f} K:{k:3.0f}ppm",
        f"P:{pump_str} F:{fert_str} Z:{active_zones_str}"
    ]

    # Water requirement
    water_req = BananaET0Calculator.calculate_daily_irrigation(
        growth_stage=zone.current_stage,
        temp_c=temp,
        rh_pct=rh,
        wind_kmh=wind,
        emitter_flow_rate_lph=zone.emitter_flow_rate_lph
    )

    # Alerts
    alerts_res = await db.execute(
        select(Alert)
        .where(Alert.zone_id == zone.id, Alert.is_resolved == False)
        .order_by(Alert.created_at.desc())
        .limit(2)
    )
    alerts = alerts_res.scalars().all()

    return {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "current_stage_th": "ระยะที่ 3: เบ่งผลทำน้ำหนัก (เดือนที่ 7.5)",
        "lcd_display": lcd_lines,
        # Row 2: Power Rails Fail-Safe Status
        "power_rails": {
            "ac_220v": True,  # 🔴 AC 220V ไฟบ้านปกติ
            "dc_24v": True,   # 🟢 DC 24V โซลินอยด์วาล์วปกติ
            "dc_12v": True    # 🟢 DC 12V บอร์ด/เซนเซอร์ปกติ
        },
        # Row 3/4: Pumps
        "pumps": {
            "water_pump": {
                "id": pump_water.id if pump_water else "dummy-water",
                "is_active": pump_water.is_active if pump_water else False,
                "label": "ปั๊มน้ำหลัก"
            },
            "fertilizer_pump": {
                "id": pump_fert.id if pump_fert else "dummy-fert",
                "is_active": pump_fert.is_active if pump_fert else False,
                "label": "ปั๊มปุ๋ย K (0-0-60)"
            }
        },
        # Row 5/6: 4 Zones
        "zones": {
            "zone_1": z1,
            "zone_2": z2,
            "zone_3": z3,
            "zone_4": z4
        },
        "soil": {
            "moisture_pct": moisture,
            "temp_c": soil_temp,
            "ec_ds_m": ec,
            "k_ppm": k,
            "ph": ph
        },
        "weather": {
            "temp_c": temp,
            "rh_pct": rh,
            "light_lux": lux,
            "wind_speed_kmh": wind
        },
        "water_recommendation": {
            "liters_per_tree": water_req["water_liters_per_tree"],
            "runtime_minutes": water_req["recommended_runtime_minutes"]
        },
        "settings": zone_automation_settings,
        "active_alerts": [
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "message": a.message,
                "action": a.suggested_action
            }
            for a in alerts
        ]
    }

@router.post("/toggle-control")
async def toggle_digital_twin_control(
    target: str = Query(..., description="WATER_PUMP, FERT_PUMP, ZONE_1, ZONE_2, ZONE_3, ZONE_4"),
    desired_state: bool = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Bi-directional Sync Endpoint for Control Box Front Panel & Mobile App.
    Accepts command from Mobile App (or ESP32 physical push-button).
    Executes safety interlocks (EC >= 1.0 blocks fertilizer pump).
    """
    target_upper = target.upper()

    # Find the matching actuator
    act_name_map = {
        "WATER_PUMP": "ปั๊มน้ำหลัก",
        "FERT_PUMP": "ปั๊มปุ๋ยโพแทสเซียม",
        "ZONE_1": "โซน 1",
        "ZONE_2": "โซน 2",
        "ZONE_3": "โซน 3",
        "ZONE_4": "โซน 4"
    }
    keyword = act_name_map.get(target_upper, "โซน 1")

    act_res = await db.execute(select(Actuator).where(Actuator.name.like(f"%{keyword}%")))
    actuator = act_res.scalars().first()
    if not actuator:
        raise HTTPException(status_code=404, detail=f"Actuator for {target} not found")

    # Safety Guard on Fertilizer Pump
    if desired_state and "FERTILIZER" in actuator.actuator_type:
        latest_tel = (await db.execute(
            select(SensorTelemetry)
            .where(SensorTelemetry.zone_id == actuator.zone_id)
            .order_by(SensorTelemetry.time.desc())
            .limit(1)
        )).scalar_one_or_none()

        if latest_tel and latest_tel.soil_ec_ds_m and latest_tel.soil_ec_ds_m >= 1.0:
            raise HTTPException(
                status_code=400,
                detail="🚨 ไม่สามารถเปิดปั๊มปุ๋ยได้เนื่องจากค่า EC ดินสูงเกิน 1.0 dS/m เสี่ยงรากกล้วยไหม้! กรุณาเปิดน้ำเปล่าชะล้างเกลือก่อน"
            )

    actuator.is_active = desired_state

    # Log action
    log = FertigationLog(
        id=str(uuid.uuid4()),
        time=datetime.now(timezone.utc),
        tenant_id=actuator.tenant_id,
        zone_id=actuator.zone_id,
        device_id=actuator.device_id,
        actuator_id=actuator.id,
        trigger_type=TriggerType.MANUAL.value,
        growth_stage="STAGE_3_FRUIT_BULKING",
        action_type=f"DIGITAL_TWIN_{target_upper}",
        duration_seconds=600 if desired_state else 0,
        notes=f"Bi-directional sync trigger: {target_upper} set to {desired_state}"
    )
    db.add(log)
    await db.commit()

    return {
        "status": "success",
        "target": target_upper,
        "is_active": actuator.is_active,
        "message": f"{actuator.name} {'เปิด' if actuator.is_active else 'ปิด'} เรียบร้อยแล้ว (Bi-directional MQTT Sync)"
    }

@router.put("/settings")
async def update_farmer_settings(
    settings_payload: Dict[str, Any] = Body(...)
):
    """
    Update Tab 3: Settings & Automation (Mode toggle, zone runtimes)
    """
    zone_automation_settings.update(settings_payload)
    return {"status": "success", "settings": zone_automation_settings}
