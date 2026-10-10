import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class TenantTier(str, enum.Enum):
    FREE_RULE_BASED = "FREE_RULE_BASED"
    PRO_AI = "PRO_AI"
    ENTERPRISE = "ENTERPRISE"

class UserRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    FARM_MANAGER = "FARM_MANAGER"
    AGRONOMIST = "AGRONOMIST"
    VIEWER = "VIEWER"

class BananaGrowthStage(str, enum.Enum):
    STAGE_1_VEGETATIVE = "STAGE_1_VEGETATIVE"
    STAGE_2_FLOWERING_BUD = "STAGE_2_FLOWERING_BUD"
    STAGE_3_FRUIT_BULKING = "STAGE_3_FRUIT_BULKING"
    STAGE_4_PRE_HARVEST = "STAGE_4_PRE_HARVEST"

class DeviceMode(str, enum.Enum):
    RULE_BASED = "RULE_BASED"
    AI_ASSISTED = "AI_ASSISTED"

class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    FAULT = "FAULT"
    MAINTENANCE = "MAINTENANCE"

class ActuatorType(str, enum.Enum):
    VALVE_IRRIGATION = "VALVE_IRRIGATION"
    PUMP_FERTILIZER_K = "PUMP_FERTILIZER_K"
    PUMP_FERTILIZER_NPK = "PUMP_FERTILIZER_NPK"
    MAIN_PUMP = "MAIN_PUMP"

class TriggerType(str, enum.Enum):
    MANUAL = "MANUAL"
    RULE_TIMER = "RULE_TIMER"
    RULE_THRESHOLD = "RULE_THRESHOLD"
    AI_FERTIGATION = "AI_FERTIGATION"
    SAFETY_CUTOFF = "SAFETY_CUTOFF"

class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class AlertType(str, enum.Enum):
    HIGH_EC_SALINITY = "HIGH_EC_SALINITY"
    WATERLOGGING_RISK = "WATERLOGGING_RISK"
    DROUGHT_STRESS = "DROUGHT_STRESS"
    HIGH_WIND_COLLAPSE = "HIGH_WIND_COLLAPSE"
    SIGATOKA_HUMIDITY_ALERT = "SIGATOKA_HUMIDITY_ALERT"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    HARDWARE_FAULT = "HARDWARE_FAULT"

# ==========================================
# 1. Tenant & Users
# ==========================================
class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    tier = Column(String(50), default=TenantTier.FREE_RULE_BASED.value, nullable=False)
    max_farms = Column(Integer, default=1, nullable=False)
    max_devices = Column(Integer, default=5, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    farms = relationship("Farm", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(50), nullable=True)
    line_user_id = Column(String(100), unique=True, nullable=True, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(50), default=UserRole.FARM_MANAGER.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="users")

# ==========================================
# 2. Farms & Zones
# ==========================================
class Farm(Base):
    __tablename__ = "farms"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float, default=0.0)
    province = Column(String(100), nullable=False)
    district = Column(String(100), nullable=True)
    total_area_rai = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="farms")
    zones = relationship("Zone", back_populates="farm", cascade="all, delete-orphan")

class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    soil_type = Column(String(100), default="Sandy Loam (ดินร่วนปนทราย)")
    field_capacity_pct = Column(Float, default=32.0, nullable=False)
    wilting_point_pct = Column(Float, default=14.0, nullable=False)
    plant_count = Column(Integer, default=400, nullable=False)
    plant_spacing_m = Column(Float, default=2.0, nullable=False)
    emitter_flow_rate_lph = Column(Float, default=70.0, nullable=False)
    planting_date = Column(DateTime(timezone=True), nullable=False)
    current_stage = Column(String(50), default=BananaGrowthStage.STAGE_1_VEGETATIVE.value, nullable=False)
    stage_override_by_ai = Column(Boolean, default=False)
    target_harvest_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="ACTIVE", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    farm = relationship("Farm", back_populates="zones")
    devices = relationship("Device", back_populates="zone")
    rule = relationship("ZoneRule", back_populates="zone", uselist=False, cascade="all, delete-orphan")
    actuators = relationship("Actuator", back_populates="zone", cascade="all, delete-orphan")

# ==========================================
# 3. Hardware Devices & Actuators
# ==========================================
class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(String(36), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True, index=True)
    device_serial = Column(String(100), unique=True, nullable=False, index=True)
    mac_address = Column(String(17), unique=True, nullable=False)
    auth_token = Column(String(255), nullable=False)
    hardware_version = Column(String(50), default="ESP32-S3-V1.0")
    firmware_version = Column(String(50), default="1.0.0")
    control_mode = Column(String(50), default=DeviceMode.RULE_BASED.value, nullable=False)
    status = Column(String(50), default=DeviceStatus.OFFLINE.value, nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    telemetry_interval_sec = Column(Integer, default=30, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    zone = relationship("Zone", back_populates="devices")
    actuators = relationship("Actuator", back_populates="device", cascade="all, delete-orphan")

class Actuator(Base):
    __tablename__ = "actuators"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(String(36), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    actuator_type = Column(String(50), nullable=False)
    relay_pin = Column(Integer, nullable=False)
    nominal_flow_rate_lpm = Column(Float, default=0.0)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    zone = relationship("Zone", back_populates="actuators")
    device = relationship("Device", back_populates="actuators")

# ==========================================
# 4. Telemetry Time-Series
# ==========================================
class SensorTelemetry(Base):
    __tablename__ = "sensor_telemetry"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    time = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    zone_id = Column(String(36), nullable=False, index=True)
    device_id = Column(String(36), nullable=False, index=True)
    
    # Soil Modbus 7-in-1
    soil_moisture_pct = Column(Float, nullable=True)
    soil_temp_c = Column(Float, nullable=True)
    soil_ec_ds_m = Column(Float, nullable=True)
    soil_ph = Column(Float, nullable=True)
    soil_n_mg_kg = Column(Float, nullable=True)
    soil_p_mg_kg = Column(Float, nullable=True)
    soil_k_mg_kg = Column(Float, nullable=True)
    
    # Microclimate & Weather
    air_temp_c = Column(Float, nullable=True)
    air_rh_pct = Column(Float, nullable=True)
    light_lux = Column(Float, nullable=True)
    solar_radiation_w_m2 = Column(Float, nullable=True)
    wind_speed_kmh = Column(Float, nullable=True)
    rain_rate_mm_h = Column(Float, default=0.0)
    
    # System
    battery_voltage = Column(Float, nullable=True)
    wifi_rssi_dbm = Column(Integer, nullable=True)

# ==========================================
# 5. Fertigation Logs
# ==========================================
class FertigationLog(Base):
    __tablename__ = "fertigation_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    time = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)
    zone_id = Column(String(36), nullable=False, index=True)
    device_id = Column(String(36), nullable=False)
    actuator_id = Column(String(36), nullable=True)
    trigger_type = Column(String(50), nullable=False)
    growth_stage = Column(String(50), nullable=False)
    action_type = Column(String(50), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    water_volume_liters = Column(Float, default=0.0)
    fertilizer_type = Column(String(100), nullable=True)
    fertilizer_grams = Column(Float, default=0.0)
    pre_soil_moisture = Column(Float, nullable=True)
    post_soil_moisture = Column(Float, nullable=True)
    pre_soil_ec = Column(Float, nullable=True)
    post_soil_ec = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

# ==========================================
# 6. Zone Automation Rules (Mode 1: Rule-Based)
# ==========================================
class ZoneRule(Base):
    __tablename__ = "zone_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(String(36), ForeignKey("zones.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Thresholds
    moisture_trigger_min_pct = Column(Float, default=70.0, nullable=False)
    moisture_cutoff_max_pct = Column(Float, default=80.0, nullable=False)
    irrigation_burst_mins = Column(Integer, default=15, nullable=False)
    irrigation_cooldown_mins = Column(Integer, default=45, nullable=False)
    
    # Safety Guards
    max_safe_ec_ds_m = Column(Float, default=0.85, nullable=False)
    ec_hard_cutoff_ds_m = Column(Float, default=1.00, nullable=False)
    wind_cutoff_kmh = Column(Float, default=30.0, nullable=False)
    
    # Potassium
    target_k_ppm = Column(Float, default=250.0)
    fertigation_days_interval = Column(Integer, default=7)
    
    schedule_cron_irrigation = Column(String(50), default="0 7,16 * * *")
    is_auto_irrigation_enabled = Column(Boolean, default=True, nullable=False)
    is_auto_fertigation_enabled = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    zone = relationship("Zone", back_populates="rule")

# ==========================================
# 7. AI Plant Assessments (Mode 2: AI-Assisted)
# ==========================================
class AIPlantAssessment(Base):
    __tablename__ = "ai_plant_assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(String(36), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(Text, nullable=False)
    
    # Predicted Phenotyping
    predicted_growth_stage = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=False)
    estimated_age_days = Column(Integer, nullable=True)
    pseudostem_girth_est_cm = Column(Float, nullable=True)
    active_leaves_count = Column(Integer, nullable=True)
    bunch_detected = Column(Boolean, default=False)
    fruit_angularity_status = Column(String(50), nullable=True)
    
    # Health Assessment
    fusarium_risk_level = Column(String(20), default="LOW")
    sigatoka_leaf_spot_detected = Column(Boolean, default=False)
    potassium_deficiency_detected = Column(Boolean, default=False)
    
    # Prescription Fertigation
    recommended_et0_water_lpd = Column(Float, nullable=True)
    recommended_fertilizer_formula = Column(String(100), nullable=True)
    ai_explanation_th = Column(Text, nullable=True)
    
    farmer_confirmed_stage = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

# ==========================================
# 8. Alerts
# ==========================================
class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(String(36), ForeignKey("zones.id", ondelete="CASCADE"), nullable=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    severity = Column(String(50), nullable=False)
    alert_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=True)
    line_notified = Column(Boolean, default=False, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
