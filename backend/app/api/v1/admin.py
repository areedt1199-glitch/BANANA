from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Tenant, Farm, Zone, Device, Actuator, Alert, ZoneRule, SensorTelemetry, FertigationLog
from app.schemas.domain import RuleUpdate, DeviceSensorConfigUpdate, FarmCreate

router = APIRouter(prefix="/admin", tags=["Admin Portal & Fleet Management"])

# In-memory mock AI quota & usage analytics for cost control
ai_quota_stats = {
    "daily_image_limit": 500,
    "images_analyzed_today": 42,
    "gemini_tokens_used_today": 128500,
    "estimated_cost_usd_today": 0.28,
    "monthly_budget_usd": 25.00
}

@router.get("/overview")
async def get_admin_overview(db: AsyncSession = Depends(get_db)):
    """
    Enterprise KPI Overview for Agribusiness Executives / SaaS Admins
    """
    tenants = (await db.execute(select(Tenant))).scalars().all()
    farms = (await db.execute(select(Farm))).scalars().all()
    zones = (await db.execute(select(Zone))).scalars().all()
    devices = (await db.execute(select(Device))).scalars().all()
    active_alerts = (await db.execute(select(Alert).where(Alert.is_resolved == False))).scalars().all()

    total_rai = sum(f.total_area_rai for f in farms)
    total_trees = sum(z.plant_count for z in zones)

    online_devices = sum(1 for d in devices if d.status == "ONLINE")
    offline_devices = len(devices) - online_devices

    return {
        "tenants_total": len(tenants),
        "farms_total": len(farms),
        "zones_total": len(zones),
        "total_area_rai": total_rai,
        "total_banana_trees": total_trees,
        "device_fleet": {
            "total": len(devices),
            "online": online_devices,
            "offline": offline_devices
        },
        "critical_alerts_count": len(active_alerts),
        "ai_quota": ai_quota_stats,
        "system_status": "OPTIMAL" if len(active_alerts) == 0 else "ATTENTION_REQUIRED"
    }

@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """
    Tenant & Farm Directory (จัดการลูกค้าเกษตรกร และระดับสิทธิ์)
    """
    tenants = (await db.execute(select(Tenant))).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "tier": t.tier,
            "max_farms": t.max_farms,
            "max_devices": t.max_devices,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat()
        }
        for t in tenants
    ]

@router.put("/tenants/{tenant_id}/tier")
async def update_tenant_tier(
    tenant_id: str,
    tier: str = Query(..., description="FREE_RULE_BASED or PRO_AI or ENTERPRISE"),
    db: AsyncSession = Depends(get_db)
):
    """
    เปิด/ปิดสิทธิ์การใช้งาน (เช่น ฟรีธรรมดา หรือเปิดฟีเจอร์ AI)
    """
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.tier = tier
    await db.commit()
    return {"status": "success", "tenant_id": tenant.id, "new_tier": tenant.tier}

@router.get("/devices")
async def list_fleet_devices(db: AsyncSession = Depends(get_db)):
    """
    หน้ารวมกล่องคอนโทรลเลอร์ทั้งหมด (MAC Address, Ping, Firmware, สัญญาณ Wi-Fi)
    """
    devices = (await db.execute(select(Device))).scalars().all()
    return [
        {
            "id": d.id,
            "serial": d.device_serial,
            "mac_address": d.mac_address,
            "hardware_version": d.hardware_version,
            "firmware_version": d.firmware_version,
            "control_mode": d.control_mode,
            "status": d.status,
            "rssi_dbm": -62,
            "last_heartbeat_at": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else datetime.now(timezone.utc).isoformat(),
            "telemetry_interval_sec": d.telemetry_interval_sec
        }
        for d in devices
    ]

@router.post("/devices/{device_id}/trigger-ota")
async def trigger_remote_ota(
    device_id: str,
    target_firmware_version: str = Query("1.1.0"),
    db: AsyncSession = Depends(get_db)
):
    """
    สั่งรีโมตอัปเดต Firmware ข้ามอากาศ (OTA Update) ผ่านคำสั่ง MQTT
    """
    device = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # In production: Publish MQTT topic homthong/{tenant_id}/{device_id}/ota_cmd
    device.firmware_version = target_firmware_version
    await db.commit()

    return {
        "status": "success",
        "device_serial": device.device_serial,
        "message": f"คำสั่ง OTA Firmware v{target_firmware_version} ส่งไปยังบอร์ด ESP32 สำเร็จ",
        "download_url": f"https://firmware.smartbanana.farm/builds/esp32_v{target_firmware_version}.bin"
    }

@router.get("/agronomy-thresholds/{zone_id}")
async def get_agronomy_thresholds(zone_id: str, db: AsyncSession = Depends(get_db)):
    """
    Agronomy Knowledge Base: อ่านเกณฑ์ค่ามาตรฐานกล้วยหอมทอง
    """
    rule = (await db.execute(select(ZoneRule).where(ZoneRule.zone_id == zone_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Zone rule not found")
    return {
        "zone_id": zone_id,
        "moisture_trigger_min_pct": rule.moisture_trigger_min_pct,
        "moisture_cutoff_max_pct": rule.moisture_cutoff_max_pct,
        "irrigation_burst_mins": rule.irrigation_burst_mins,
        "max_safe_ec_ds_m": rule.max_safe_ec_ds_m,
        "ec_hard_cutoff_ds_m": rule.ec_hard_cutoff_ds_m,
        "wind_cutoff_kmh": rule.wind_cutoff_kmh,
        "target_k_ppm": rule.target_k_ppm,
        "fertigation_days_interval": rule.fertigation_days_interval,
        "is_auto_irrigation_enabled": rule.is_auto_irrigation_enabled,
        "is_auto_fertigation_enabled": rule.is_auto_fertigation_enabled
    }

@router.put("/agronomy-thresholds/{zone_id}")
async def update_agronomy_thresholds(
    zone_id: str,
    payload: RuleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Agronomy Knowledge Base: ปรับปรุงเกณฑ์ค่ามาตรฐานกล้วยหอมทอง โดยไม่ต้องแก้โค้ดใหม่
    """
    rule = (await db.execute(select(ZoneRule).where(ZoneRule.zone_id == zone_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Zone rule not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    rule.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "success", "message": "อัปเดตเกณฑ์มาตรฐานทางสรีรวิทยาสำเร็จ"}

@router.get("/ai-quota-analytics")
async def get_ai_quota_analytics():
    """
    AI & API Quota Analytics: มอนิเตอร์จำนวน Token และภาพถ่ายเพื่อคุมต้นทุน
    """
    return ai_quota_stats

# ==============================================================================
# Multi-Farm & Per-Farm Sensor Configuration APIs (Enterprise Scalable)
# ==============================================================================
@router.get("/farms")
async def list_farms(db: AsyncSession = Depends(get_db)):
    """
    ดึงรายชื่อฟาร์มทั้งหมด พร้อมโซนและอุปกรณ์ภายใต้ฟาร์มนั้น (Multi-Farm Management)
    """
    farms = (await db.execute(select(Farm))).scalars().all()
    results = []
    for f in farms:
        zones = (await db.execute(select(Zone).where(Zone.farm_id == f.id))).scalars().all()
        devices = (await db.execute(select(Device).where(Device.farm_id == f.id))).scalars().all()
        results.append({
            "id": f.id,
            "tenant_id": f.tenant_id,
            "name": f.name,
            "province": f.province,
            "district": f.district,
            "latitude": f.latitude,
            "longitude": f.longitude,
            "total_area_rai": f.total_area_rai,
            "zone_count": len(zones),
            "device_count": len(devices),
            "zones": [{"id": z.id, "name": z.name, "current_stage": z.current_stage} for z in zones],
            "devices": [{
                "id": d.id,
                "serial": d.device_serial,
                "status": d.status,
                "sensor_model": getattr(d, 'sensor_model', 'SN-3002GZWS-NO1-65535'),
                "baud_rate": getattr(d, 'baud_rate', 9600),
                "modbus_slave_id": getattr(d, 'modbus_slave_id', 1),
                "telemetry_interval_sec": d.telemetry_interval_sec,
                "temp_offset": getattr(d, 'temp_offset', 0.0),
                "rh_offset": getattr(d, 'rh_offset', 0.0),
                "lux_offset": getattr(d, 'lux_offset', 0.0),
                "ec_offset": getattr(d, 'ec_offset', 0.0),
                "ph_offset": getattr(d, 'ph_offset', 0.0)
            } for d in devices]
        })
    return results

@router.post("/farms")
async def create_new_farm(payload: FarmCreate, db: AsyncSession = Depends(get_db)):
    """
    เพิ่มฟาร์มใหม่ พร้อมสร้างแปลงและกล่องอุปกรณ์เริ่มต้นสำหรับฟาร์มนั้นแบบ Isolated
    """
    tenant = (await db.execute(select(Tenant))).scalars().first()
    tenant_id = payload.tenant_id or (tenant.id if tenant else str(uuid.uuid4()))
    
    farm = Farm(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=payload.name,
        province=payload.province,
        district=payload.district or "เมือง",
        latitude=payload.latitude,
        longitude=payload.longitude,
        total_area_rai=payload.total_area_rai
    )
    db.add(farm)
    await db.flush()
    
    # สร้างโซนเริ่มต้นของฟาร์มนี้
    zone = Zone(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        farm_id=farm.id,
        name=f"แปลงที่ 1 ({farm.name})",
        soil_type="Sandy Loam (ดินร่วนปนทราย)",
        field_capacity_pct=32.0,
        wilting_point_pct=14.0,
        plant_count=int(farm.total_area_rai * 400),
        planting_date=datetime.now(timezone.utc),
        current_stage="STAGE_3_FRUIT_BULKING"
    )
    db.add(zone)
    await db.flush()
    
    # สร้างเกณฑ์สำหรับโซนนี้
    rule = ZoneRule(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        zone_id=zone.id,
        moisture_trigger_min_pct=72.0,
        moisture_cutoff_max_pct=82.0,
        irrigation_burst_mins=15,
        max_safe_ec_ds_m=0.85,
        ec_hard_cutoff_ds_m=1.00,
        wind_cutoff_kmh=30.0,
        target_k_ppm=280.0
    )
    db.add(rule)
    
    # สร้างกล่องอุปกรณ์ประจำฟาร์มนี้
    dev_count = len((await db.execute(select(Device))).scalars().all()) + 1
    device = Device(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        farm_id=farm.id,
        zone_id=zone.id,
        device_serial=f"ESP32-BANANA-{dev_count:03d}",
        mac_address=f"A4:CF:12:89:FE:{dev_count:02X}",
        auth_token=str(uuid.uuid4()),
        hardware_version="ESP32-S3-V1.0",
        firmware_version="1.0.0",
        control_mode="RULE_BASED",
        status="ONLINE",
        sensor_model="SN-3002GZWS-NO1-65535",
        baud_rate=9600,
        modbus_slave_id=1,
        telemetry_interval_sec=30
    )
    db.add(device)
    await db.commit()
    
    return {
        "status": "success",
        "message": f"เพิ่มฟาร์ม '{farm.name}' สำเร็จ พร้อมเชื่อมต่อกล่อง {device.device_serial}",
        "farm_id": farm.id,
        "zone_id": zone.id,
        "device_serial": device.device_serial
    }

@router.get("/farms/{farm_id}/details")
async def get_farm_details(farm_id: str, db: AsyncSession = Depends(get_db)):
    """
    ดึงข้อมูลการตั้งค่าแบบละเอียดของฟาร์มที่เลือก (อุปกรณ์, เซนเซอร์, เกณฑ์การเกษตร)
    """
    farm = (await db.execute(select(Farm).where(Farm.id == farm_id))).scalar_one_or_none()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
        
    zones = (await db.execute(select(Zone).where(Zone.farm_id == farm.id))).scalars().all()
    devices = (await db.execute(select(Device).where(Device.farm_id == farm.id))).scalars().all()
    
    # ดึง rules ของแต่ละโซน
    zone_details = []
    for z in zones:
        rule = (await db.execute(select(ZoneRule).where(ZoneRule.zone_id == z.id))).scalar_one_or_none()
        zone_details.append({
            "id": z.id,
            "name": z.name,
            "soil_type": z.soil_type,
            "current_stage": z.current_stage,
            "rule": {
                "moisture_trigger_min_pct": rule.moisture_trigger_min_pct if rule else 72.0,
                "moisture_cutoff_max_pct": rule.moisture_cutoff_max_pct if rule else 82.0,
                "max_safe_ec_ds_m": rule.max_safe_ec_ds_m if rule else 0.85,
                "ec_hard_cutoff_ds_m": rule.ec_hard_cutoff_ds_m if rule else 1.00,
                "wind_cutoff_kmh": rule.wind_cutoff_kmh if rule else 30.0,
                "target_k_ppm": rule.target_k_ppm if rule else 280.0,
                "is_auto_irrigation_enabled": rule.is_auto_irrigation_enabled if rule else True
            } if rule else None
        })
        
    device_details = [{
        "id": d.id,
        "device_serial": d.device_serial,
        "zone_id": d.zone_id,
        "status": d.status,
        "sensor_model": getattr(d, 'sensor_model', 'SN-3002GZWS-NO1-65535'),
        "baud_rate": getattr(d, 'baud_rate', 9600),
        "modbus_slave_id": getattr(d, 'modbus_slave_id', 1),
        "telemetry_interval_sec": d.telemetry_interval_sec,
        "temp_offset": getattr(d, 'temp_offset', 0.0),
        "rh_offset": getattr(d, 'rh_offset', 0.0),
        "lux_offset": getattr(d, 'lux_offset', 0.0),
        "ec_offset": getattr(d, 'ec_offset', 0.0),
        "ph_offset": getattr(d, 'ph_offset', 0.0)
    } for d in devices]
    
    return {
        "id": farm.id,
        "name": farm.name,
        "province": farm.province,
        "district": farm.district,
        "total_area_rai": farm.total_area_rai,
        "zones": zone_details,
        "devices": device_details
    }

@router.get("/devices/{device_id}/config")
async def get_device_config(device_id: str, db: AsyncSession = Depends(get_db)):
    """
    ดึงการตั้งค่าของอุปกรณ์ตัวนี้ (สำหรับให้ Gateway หรือ Edge Controller ดึงไปใช้)
    """
    device = (await db.execute(select(Device).where(
        (Device.id == device_id) | (Device.device_serial == device_id)
    ))).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    return {
        "device_id": device.id,
        "device_serial": device.device_serial,
        "farm_id": device.farm_id,
        "zone_id": device.zone_id,
        "sensor_model": getattr(device, 'sensor_model', 'SN-3002GZWS-NO1-65535'),
        "baud_rate": getattr(device, 'baud_rate', 9600),
        "modbus_slave_id": getattr(device, 'modbus_slave_id', 1),
        "telemetry_interval_sec": device.telemetry_interval_sec,
        "offsets": {
            "temp": getattr(device, 'temp_offset', 0.0),
            "rh": getattr(device, 'rh_offset', 0.0),
            "lux": getattr(device, 'lux_offset', 0.0),
            "ec": getattr(device, 'ec_offset', 0.0),
            "ph": getattr(device, 'ph_offset', 0.0)
        }
    }

@router.put("/devices/{device_id}/sensor-config")
async def update_device_sensor_config(
    device_id: str,
    payload: DeviceSensorConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    ปรับแต่งค่าเซนเซอร์และการสื่อสารของอุปกรณ์ตัวนี้โดยเฉพาะ (แยกรายฟาร์ม 100%)
    """
    device = (await db.execute(select(Device).where(
        (Device.id == device_id) | (Device.device_serial == device_id)
    ))).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        if hasattr(device, k):
            setattr(device, k, v)

    device.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "success",
        "message": f"บันทึกการตั้งค่าเซนเซอร์สำหรับอุปกรณ์ {device.device_serial} สำเร็จ",
        "device_serial": device.device_serial,
        "farm_id": device.farm_id,
        "updated_config": {
            "sensor_model": getattr(device, 'sensor_model', 'SN-3002GZWS-NO1-65535'),
            "baud_rate": getattr(device, 'baud_rate', 9600),
            "modbus_slave_id": getattr(device, 'modbus_slave_id', 1),
            "telemetry_interval_sec": device.telemetry_interval_sec,
            "temp_offset": getattr(device, 'temp_offset', 0.0),
            "rh_offset": getattr(device, 'rh_offset', 0.0),
            "lux_offset": getattr(device, 'lux_offset', 0.0),
            "ec_offset": getattr(device, 'ec_offset', 0.0),
            "ph_offset": getattr(device, 'ph_offset', 0.0)
        }
    }
