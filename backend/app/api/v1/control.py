from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Actuator, Zone, ZoneRule, FertigationLog, TriggerType, SensorTelemetry
from app.schemas.domain import ActuatorCommand

router = APIRouter(prefix="/control", tags=["Actuator Control & Fertigation"])

@router.get("/actuators/{zone_id}")
async def list_actuators(zone_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Actuator).where(Actuator.zone_id == zone_id))
    actuators = result.scalars().all()
    return actuators

@router.post("/override")
async def manual_actuator_override(
    cmd: ActuatorCommand,
    db: AsyncSession = Depends(get_db)
):
    """
    Manual override switch for farmer (via Web Dashboard or LINE LIFF).
    Includes safety guard: blocks fertilizer pump if soil EC is dangerously high (> 1.0 dS/m).
    """
    act_res = await db.execute(select(Actuator).where(Actuator.id == cmd.actuator_id))
    actuator = act_res.scalar_one_or_none()
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    zone_res = await db.execute(select(Zone).where(Zone.id == actuator.zone_id))
    zone = zone_res.scalar_one_or_none()

    # Safety Guard on Manual Fertilizer Dosing
    if cmd.action == "START" and "FERTILIZER" in actuator.actuator_type:
        # Check latest EC
        latest_tel_res = await db.execute(
            select(SensorTelemetry)
            .where(SensorTelemetry.zone_id == actuator.zone_id)
            .order_by(SensorTelemetry.time.desc())
            .limit(1)
        )
        latest_tel = latest_tel_res.scalar_one_or_none()
        if latest_tel and latest_tel.soil_ec_ds_m and latest_tel.soil_ec_ds_m >= 1.0:
            raise HTTPException(
                status_code=400,
                detail=f"🚨 SAFETY INTERLOCK: ไม่สามารถเปิดปั๊มปุ๋ยได้เนื่องจากค่า EC ในดินสูงวิกฤต ({latest_tel.soil_ec_ds_m} dS/m >= 1.0 dS/m) เสี่ยงรากกล้วยหอมทองไหม้ กรุณาเปิดน้ำเปล่าชะล้างก่อน"
            )

    new_state = (cmd.action == "START")
    actuator.is_active = new_state

    # Log manual action
    log = FertigationLog(
        id=str(uuid.uuid4()),
        time=datetime.now(timezone.utc),
        tenant_id=actuator.tenant_id,
        zone_id=actuator.zone_id,
        device_id=actuator.device_id,
        actuator_id=actuator.id,
        trigger_type=TriggerType.MANUAL.value,
        growth_stage=zone.current_stage if zone else "UNKNOWN",
        action_type="MANUAL_PUMP" if "FERTILIZER" in actuator.actuator_type else "MANUAL_VALVE",
        duration_seconds=cmd.duration_seconds or 600,
        fertilizer_type=cmd.fertilizer_formula,
        notes=f"Manual command: {cmd.override_reason}"
    )
    db.add(log)
    await db.commit()

    return {
        "status": "success",
        "actuator_id": actuator.id,
        "name": actuator.name,
        "is_active": actuator.is_active,
        "message": f"{actuator.name} {'เปิดทำงาน' if new_state else 'ปิดการทำงาน'} เรียบร้อยแล้ว"
    }
