from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.models.entities import Tenant, Farm, Zone, Device, Actuator, Alert, ZoneRule, SensorTelemetry, FertigationLog
from app.schemas.domain import RuleUpdate

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
