from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

# ==========================================
# Telemetry Schemas
# ==========================================
class TelemetryCreate(BaseModel):
    tenant_id: str
    zone_id: str
    device_id: str
    time: Optional[datetime] = None
    
    # Soil Modbus 7-in-1
    soil_moisture_pct: float = Field(..., ge=0, le=100, description="ความชื้นในดิน (% FC)")
    soil_temp_c: float = Field(..., ge=-10, le=70, description="อุณหภูมิดิน (°C)")
    soil_ec_ds_m: float = Field(..., ge=0, le=10, description="ความเค็มดิน EC (dS/m) กล้วยหอมทองห้ามเกิน 1.0")
    soil_ph: float = Field(..., ge=0, le=14, description="ความเป็นกรด-ด่างดิน (pH)")
    soil_n_mg_kg: float = Field(..., ge=0, description="ไนโตรเจน (mg/kg)")
    soil_p_mg_kg: float = Field(..., ge=0, description="ฟอสฟอรัส (mg/kg)")
    soil_k_mg_kg: float = Field(..., ge=0, description="โพแทสเซียม (mg/kg)")

    # Microclimate & Weather
    air_temp_c: float = Field(..., description="อุณหภูมิอากาศ (°C)")
    air_rh_pct: float = Field(..., ge=0, le=100, description="ความชื้นสัมพัทธ์อากาศ (% RH)")
    light_lux: float = Field(..., ge=0, description="ความเข้มแสง (Lux)")
    solar_radiation_w_m2: Optional[float] = Field(default=0.0, description="รังสีดวงอาทิตย์ (W/m²)")
    wind_speed_kmh: float = Field(..., ge=0, description="ความเร็วลม (km/h) > 30 เสี่ยงต้นหัก")
    rain_rate_mm_h: Optional[float] = Field(default=0.0)

    battery_voltage: Optional[float] = Field(default=4.1)
    wifi_rssi_dbm: Optional[int] = Field(default=-65)

class TelemetryResponse(TelemetryCreate):
    id: str

    class Config:
        from_attributes = True

# ==========================================
# Zone & Agronomic Schemas
# ==========================================
class ZoneCreate(BaseModel):
    farm_id: str
    name: str
    soil_type: Optional[str] = "Sandy Loam (ดินร่วนปนทราย)"
    field_capacity_pct: float = 32.0
    wilting_point_pct: float = 14.0
    plant_count: int = 400
    plant_spacing_m: float = 2.0
    emitter_flow_rate_lph: float = 70.0
    planting_date: datetime
    current_stage: str = "STAGE_1_VEGETATIVE"

class ZoneResponse(BaseModel):
    id: str
    tenant_id: str
    farm_id: str
    name: str
    soil_type: str
    field_capacity_pct: float
    wilting_point_pct: float
    plant_count: int
    current_stage: str
    stage_override_by_ai: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Rule & Control Schemas
# ==========================================
class RuleUpdate(BaseModel):
    moisture_trigger_min_pct: Optional[float] = 70.0
    moisture_cutoff_max_pct: Optional[float] = 80.0
    irrigation_burst_mins: Optional[int] = 15
    irrigation_cooldown_mins: Optional[int] = 45
    max_safe_ec_ds_m: Optional[float] = 0.85
    ec_hard_cutoff_ds_m: Optional[float] = 1.00
    wind_cutoff_kmh: Optional[float] = 30.0
    target_k_ppm: Optional[float] = 250.0
    fertigation_days_interval: Optional[int] = 7
    is_auto_irrigation_enabled: Optional[bool] = True
    is_auto_fertigation_enabled: Optional[bool] = False

class ActuatorCommand(BaseModel):
    actuator_id: str
    action: str  # "START" or "STOP"
    duration_seconds: Optional[int] = 600
    fertilizer_formula: Optional[str] = None
    override_reason: Optional[str] = "Manual farmer control"

# ==========================================
# AI Phenotyping Schemas
# ==========================================
class AIPlantAssessmentResponse(BaseModel):
    id: str
    tenant_id: str
    zone_id: str
    image_url: str
    predicted_growth_stage: str
    confidence_score: float
    estimated_age_days: Optional[int]
    pseudostem_girth_est_cm: Optional[float]
    active_leaves_count: Optional[int]
    bunch_detected: bool
    fruit_angularity_status: Optional[str]
    fusarium_risk_level: str
    sigatoka_leaf_spot_detected: bool
    potassium_deficiency_detected: bool
    recommended_et0_water_lpd: Optional[float]
    recommended_fertilizer_formula: Optional[str]
    ai_explanation_th: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Alert Schemas
# ==========================================
class AlertResponse(BaseModel):
    id: str
    tenant_id: str
    zone_id: Optional[str]
    severity: str
    alert_type: str
    title: str
    message: str
    suggested_action: Optional[str]
    line_notified: bool
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Device & Farm Sensor Configuration Schemas
# ==========================================
class DeviceSensorConfigUpdate(BaseModel):
    sensor_model: Optional[str] = "SN-3002GZWS-NO1-65535"
    baud_rate: Optional[int] = 9600
    modbus_slave_id: Optional[int] = 1
    telemetry_interval_sec: Optional[int] = 30
    temp_offset: Optional[float] = 0.0
    rh_offset: Optional[float] = 0.0
    lux_offset: Optional[float] = 0.0
    ec_offset: Optional[float] = 0.0
    ph_offset: Optional[float] = 0.0

class FarmCreate(BaseModel):
    tenant_id: Optional[str] = None
    name: str
    province: str
    district: Optional[str] = "เมือง"
    latitude: float = 14.15
    longitude: float = 100.75
    total_area_rai: float = 5.0
