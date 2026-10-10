from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Tenant, Farm, Zone, ZoneRule, Device, Actuator, ActuatorType, BananaGrowthStage
from app.schemas.domain import ZoneResponse, ZoneCreate

router = APIRouter(prefix="/zones", tags=["Zones & Plots"])

@router.get("/", response_model=List[ZoneResponse])
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone))
    zones = result.scalars().all()
    return zones

@router.get("/{zone_id}", response_model=ZoneResponse)
async def get_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone

@router.post("/seed-demo-farm")
async def seed_demo_farm(db: AsyncSession = Depends(get_db)):
    """
    Seed initial Kluai Hom Thong demo tenant, farm, zone, rules, and complete 4-zone + 2-pump actuators.
    Matches the 6-row physical control box specification!
    """
    tenant_res = await db.execute(select(Tenant).where(Tenant.slug == "homthong-demo"))
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name="ฟาร์มกล้วยหอมทอง พรีเมียม (สหกรณ์แปลงใหญ่)",
            slug="homthong-demo",
            tier="PRO_AI",
            max_farms=5,
            max_devices=20
        )
        db.add(tenant)
        await db.flush()

    farm_res = await db.execute(select(Farm).where(Farm.tenant_id == tenant.id))
    farm = farm_res.scalar_one_or_none()
    if not farm:
        farm = Farm(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            name="แปลงใหญ่กล้วยหอมทองเพื่อการส่งออก โซนปทุมธานี",
            latitude=14.0205,
            longitude=100.5283,
            elevation_m=5.0,
            province="ปทุมธานี",
            district="คลองหลวง",
            total_area_rai=10.0
        )
        db.add(farm)
        await db.flush()

    zone_res = await db.execute(select(Zone).where(Zone.farm_id == farm.id))
    zone = zone_res.scalar_one_or_none()
    if not zone:
        zone = Zone(
            id="d5fcc075-5ae5-4b88-9b03-1aa904b28e43",
            tenant_id=tenant.id,
            farm_id=farm.id,
            name="แปลงที่ 1: กล้วยหอมทอง (ระยะเบ่งผลทำน้ำหนัก - เดือนที่ 7.5)",
            soil_type="ดินร่วนปนทราย (Sandy Loam)",
            field_capacity_pct=34.0,
            wilting_point_pct=15.0,
            plant_count=400,
            plant_spacing_m=2.0,
            emitter_flow_rate_lph=70.0,
            planting_date=datetime.now(timezone.utc),
            current_stage=BananaGrowthStage.STAGE_3_FRUIT_BULKING.value,
            status="ACTIVE"
        )
        db.add(zone)
        await db.flush()

    # Hardware Device Controller (ESP32-S3)
    dev_res = await db.execute(select(Device).where(Device.device_serial == "ESP32-BANANA-001"))
    device = dev_res.scalar_one_or_none()
    if not device:
        device = Device(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            farm_id=farm.id,
            zone_id=zone.id,
            device_serial="ESP32-BANANA-001",
            mac_address="A4:CF:12:89:FE:20",
            auth_token="esp32_secret_token_homthong_2026",
            hardware_version="ESP32-S3-V1.0 (Modbus+LCD2004)",
            firmware_version="1.0.0",
            control_mode="RULE_BASED",
            status="ONLINE",
            last_heartbeat_at=datetime.now(timezone.utc),
            telemetry_interval_sec=30
        )
        db.add(device)
        await db.flush()

    # Zone Rules
    rule_res = await db.execute(select(ZoneRule).where(ZoneRule.zone_id == zone.id))
    rule = rule_res.scalar_one_or_none()
    if not rule:
        rule = ZoneRule(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            zone_id=zone.id,
            moisture_trigger_min_pct=72.0,
            moisture_cutoff_max_pct=82.0,
            irrigation_burst_mins=15,
            max_safe_ec_ds_m=0.85,
            ec_hard_cutoff_ds_m=1.00,
            wind_cutoff_kmh=30.0,
            target_k_ppm=280.0,
            is_auto_irrigation_enabled=True,
            is_auto_fertigation_enabled=True
        )
        db.add(rule)

    # Actuators matching the 6-row physical control box!
    # Row 3: Water Pump & Fertilizer Pump
    # Row 5: Zone 1, Zone 2, Zone 3, Zone 4
    actuators_specs = [
        {"name": "ปั๊มน้ำหลัก (Main Water Pump)", "type": "MAIN_PUMP", "pin": 21, "flow": 500.0, "code": "PUMP_WATER"},
        {"name": "ปั๊มปุ๋ยโพแทสเซียม K (0-0-60 Potash)", "type": "PUMP_FERTILIZER_K", "pin": 22, "flow": 5.0, "code": "PUMP_FERT"},
        {"name": "โซลินอยด์วาล์ว โซน 1 (Zone 1 Valve)", "type": "VALVE_IRRIGATION", "pin": 23, "flow": 120.0, "code": "VALVE_Z1"},
        {"name": "โซลินอยด์วาล์ว โซน 2 (Zone 2 Valve)", "type": "VALVE_IRRIGATION", "pin": 25, "flow": 120.0, "code": "VALVE_Z2"},
        {"name": "โซลินอยด์วาล์ว โซน 3 (Zone 3 Valve)", "type": "VALVE_IRRIGATION", "pin": 26, "flow": 120.0, "code": "VALVE_Z3"},
        {"name": "โซลินอยด์วาล์ว โซน 4 (Zone 4 Valve)", "type": "VALVE_IRRIGATION", "pin": 27, "flow": 120.0, "code": "VALVE_Z4"}
    ]

    for spec in actuators_specs:
        existing = (await db.execute(select(Actuator).where(Actuator.name == spec["name"]))).scalar_one_or_none()
        if not existing:
            act = Actuator(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                zone_id=zone.id,
                device_id=device.id,
                name=spec["name"],
                actuator_type=spec["type"],
                relay_pin=spec["pin"],
                nominal_flow_rate_lpm=spec["flow"],
                is_active=False
            )
            db.add(act)

    await db.commit()
    return {
        "status": "success",
        "message": "Demo farm and 6-row physical actuators seeded successfully",
        "tenant_id": tenant.id,
        "farm_id": farm.id,
        "zone_id": zone.id,
        "device_id": device.id
    }
