-- ==============================================================================
-- SMART BANANA IOT & AI PLATFORM (กล้วยหอมทอง - KLUAI HOM THONG)
-- Multi-Tenant Database Schema with TimescaleDB Time-Series Support
-- Phase 1: Database Initialization Script
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;

-- 2. Enumerations (Custom Types)
CREATE TYPE tenant_tier_enum AS ENUM ('FREE_RULE_BASED', 'PRO_AI', 'ENTERPRISE');
CREATE TYPE user_role_enum AS ENUM ('SUPERADMIN', 'TENANT_ADMIN', 'FARM_MANAGER', 'AGRONOMIST', 'VIEWER');
CREATE TYPE banana_growth_stage_enum AS ENUM (
    'STAGE_1_VEGETATIVE',      -- เดือน 1-4: สะสมต้นและใบ (25-30 ใบ), ชื้น 65-75% FC, EC 0.2-0.5, N:P:K = 2:1:2
    'STAGE_2_FLOWERING_BUD',   -- เดือน 5-6: สร้างตาดอก แทงปลี, ชื้น 70-80% FC, EC 0.4-0.7, N:P:K = 1:1:2-3
    'STAGE_3_FRUIT_BULKING',    -- เดือน 7-8.5: เบ่งผล/ทำน้ำหนัก, ชื้น 75-85% FC, EC 0.5-0.8 (ห้ามเกิน 1.0), N:P:K = 1:0.5:4 (เน้น K สูง)
    'STAGE_4_PRE_HARVEST'      -- เดือน 9: ก่อนตัด 2-3 สัปดาห์ ลดน้ำเหลือ 55-65% FC, งดน้ำก่อนตัด 7-10 วัน
);
CREATE TYPE device_mode_enum AS ENUM ('RULE_BASED', 'AI_ASSISTED');
CREATE TYPE device_status_enum AS ENUM ('ONLINE', 'OFFLINE', 'FAULT', 'MAINTENANCE');
CREATE TYPE actuator_type_enum AS ENUM ('VALVE_IRRIGATION', 'PUMP_FERTILIZER_K', 'PUMP_FERTILIZER_NPK', 'MAIN_PUMP');
CREATE TYPE trigger_type_enum AS ENUM ('MANUAL', 'RULE_TIMER', 'RULE_THRESHOLD', 'AI_FERTIGATION', 'SAFETY_CUTOFF');
CREATE TYPE alert_severity_enum AS ENUM ('INFO', 'WARNING', 'CRITICAL');
CREATE TYPE alert_type_enum AS ENUM (
    'HIGH_EC_SALINITY',        -- EC > 0.8 - 1.0 dS/m (กล้วยหอมทองรากไหม้ ชะงักการโต)
    'WATERLOGGING_RISK',       -- ความชื้นอิ่มตัวต่อเนื่อง > 48 ชม. เสี่ยงรากเน่า/Fusarium
    'DROUGHT_STRESS',          -- ความชื้นต่ำกว่าขีดจำกัดวิกฤต
    'HIGH_WIND_COLLAPSE',      -- ลมกระโชกแรง > 30 km/h เสี่ยงต้นหักโค่นช่วงติดผล
    'SIGATOKA_HUMIDITY_ALERT', -- ความชื้นสัมพัทธ์ > 90% สะสม > 10 ชั่วโมง (เสี่ยงโรคใบจุด)
    'DEVICE_OFFLINE',          -- บอร์ด ESP32 ไม่ส่งสัญญาณ Heartbeat
    'HARDWARE_FAULT'           -- เซนเซอร์ 7-in-1 หรือ Relay อ่านค่าผิดปกติ
);

-- ==============================================================================
-- 3. Core Multi-Tenancy & User Management Tables
-- ==============================================================================

-- 3.1 Tenants (องค์กร / สหกรณ์ / เจ้าของแปลงใหญ่)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    tier tenant_tier_enum DEFAULT 'FREE_RULE_BASED' NOT NULL,
    max_farms INT DEFAULT 1 NOT NULL,
    max_devices INT DEFAULT 5 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- 3.2 Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE,
    phone_number VARCHAR(50),
    line_user_id VARCHAR(100) UNIQUE, -- ผูกกับ LINE Official Account / LIFF
    full_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    role user_role_enum DEFAULT 'FARM_MANAGER' NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_line_user_id ON users(line_user_id);

-- ==============================================================================
-- 4. Agronomic Hierarchy: Farms & Planting Zones (แปลงปลูก)
-- ==============================================================================

-- 4.1 Farms (ฟาร์ม/สวน)
CREATE TABLE farms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    elevation_m NUMERIC(6, 2) DEFAULT 0.0,
    province VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    total_area_rai NUMERIC(6, 2) DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_farms_tenant_id ON farms(tenant_id);

-- 4.2 Zones (แปลงย่อย / โซนจัดการให้น้ำและปุ๋ย)
CREATE TABLE zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    farm_id UUID NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    soil_type VARCHAR(100) DEFAULT 'Sandy Loam (ดินร่วนปนทราย)',
    field_capacity_pct NUMERIC(5, 2) DEFAULT 32.0 NOT NULL,     -- ความชื้นชลประทาน (% FC)
    wilting_point_pct NUMERIC(5, 2) DEFAULT 14.0 NOT NULL,      -- จุดเหี่ยวเฉาถาวร (% PWP)
    plant_count INT DEFAULT 400 NOT NULL,                        -- จำนวนต้นกล้วยในโซน (ปกติ ~400 ต้น/ไร่ ที่ระยะ 2x2 ม.)
    plant_spacing_m NUMERIC(4, 2) DEFAULT 2.0 NOT NULL,          -- ระยะห่างระหว่างต้น (เมตร)
    emitter_flow_rate_lph NUMERIC(6, 2) DEFAULT 70.0 NOT NULL,   -- อัตราการจ่ายน้ำของหัวมินิสปริงเกลอร์ (ลิตร/ชม./ต้น)
    planting_date DATE NOT NULL,                                 -- วันที่เริ่มปลูกหน่อ
    current_stage banana_growth_stage_enum DEFAULT 'STAGE_1_VEGETATIVE' NOT NULL,
    stage_override_by_ai BOOLEAN DEFAULT FALSE,
    target_harvest_date DATE,
    status VARCHAR(50) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_zones_tenant_id ON zones(tenant_id);
CREATE INDEX idx_zones_farm_id ON zones(farm_id);

-- ==============================================================================
-- 5. Hardware Device Registry & Actuator Mapping
-- ==============================================================================

-- 5.1 Devices (ESP32-S3 Controllers)
CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    farm_id UUID NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    zone_id UUID REFERENCES zones(id) ON DELETE SET NULL,
    device_serial VARCHAR(100) UNIQUE NOT NULL,                  -- เช่น ESP32-BANANA-001
    mac_address VARCHAR(17) UNIQUE NOT NULL,
    auth_token VARCHAR(255) NOT NULL,                            -- Token สำหรับยืนยันสิทธิ์ MQTT / API
    hardware_version VARCHAR(50) DEFAULT 'ESP32-S3-V1.0',
    firmware_version VARCHAR(50) DEFAULT '1.0.0',
    control_mode device_mode_enum DEFAULT 'RULE_BASED' NOT NULL,
    status device_status_enum DEFAULT 'OFFLINE' NOT NULL,
    last_heartbeat_at TIMESTAMPTZ,
    telemetry_interval_sec INT DEFAULT 30 NOT NULL,              -- ความถี่ส่งข้อมูล (วินาที)
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_devices_tenant_zone ON devices(tenant_id, zone_id);
CREATE INDEX idx_devices_serial ON devices(device_serial);

-- 5.2 Actuators (Solenoid Valve & Dosing Pumps)
CREATE TABLE actuators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,                                  -- เช่น 'โซลินอยด์วาล์วน้ำโซน 1', 'ปั๊มปุ๋ยโพแทสเซียม'
    actuator_type actuator_type_enum NOT NULL,
    relay_pin INT NOT NULL,                                      -- หมายเลข GPIO หรือ Relay Channel
    nominal_flow_rate_lpm NUMERIC(6, 2) DEFAULT 0.0,             -- อัตราไหล (ลิตร/นาที)
    is_active BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_actuators_device ON actuators(device_id);
CREATE INDEX idx_actuators_zone ON actuators(zone_id);

-- ==============================================================================
-- 6. Time-Series Telemetry (TimescaleDB Hypertable)
-- ==============================================================================

-- 6.1 Raw Sensor Telemetry Table
CREATE TABLE sensor_telemetry (
    time TIMESTAMPTZ NOT NULL,
    tenant_id UUID NOT NULL,
    zone_id UUID NOT NULL,
    device_id UUID NOT NULL,
    
    -- Soil Sensor 7-in-1 (Modbus RS485)
    soil_moisture_pct NUMERIC(5, 2),   -- ความชื้นในดิน (0-100%)
    soil_temp_c NUMERIC(5, 2),         -- อุณหภูมิดิน (°C)
    soil_ec_ds_m NUMERIC(5, 3),        -- ความเค็ม/ค่านำไฟฟ้า (dS/m หรือ mS/cm) **ห้ามเกิน 1.0**
    soil_ph NUMERIC(4, 2),             -- กรด-ด่างดิน (pH 5.5 - 6.5 เหมาะสมที่สุด)
    soil_n_mg_kg NUMERIC(6, 2),        -- ไนโตรเจนในดิน (mg/kg หรือ ppm)
    soil_p_mg_kg NUMERIC(6, 2),        -- ฟอสฟอรัสในดิน (mg/kg หรือ ppm)
    soil_k_mg_kg NUMERIC(6, 2),        -- โพแทสเซียมในดิน (mg/kg หรือ ppm) **เป้าหมายสำคัญ**

    -- Air & Microclimate (SHT30 + BH1750 + Anemometer)
    air_temp_c NUMERIC(5, 2),          -- อุณหภูมิอากาศ (°C)
    air_rh_pct NUMERIC(5, 2),          -- ความชื้นสัมพัทธ์ในอากาศ (% RH)
    light_lux NUMERIC(8, 2),           -- ความเข้มแสง (Lux)
    solar_radiation_w_m2 NUMERIC(7, 2),-- รังสีดวงอาทิตย์ (สำหรับคำนวณ ET0)
    wind_speed_kmh NUMERIC(5, 2),      -- ความเร็วลม (km/h) **>30 เสี่ยงต้นหัก**
    rain_rate_mm_h NUMERIC(5, 2) DEFAULT 0.0,

    -- System Diagnostics
    battery_voltage NUMERIC(4, 2),
    wifi_rssi_dbm INT
);

-- แปลงให้เป็น TimescaleDB Hypertable (Partition ตามคอลัมน์ time ทุกๆ 7 วัน)
SELECT create_hypertable('sensor_telemetry', 'time', chunk_time_interval => INTERVAL '7 days');

-- สร้างดัชนี Composite สำหรับคิวรี่ข้อมูลด่วนตาม Tenant, Zone และ Time
CREATE INDEX idx_telemetry_tenant_zone_time ON sensor_telemetry (tenant_id, zone_id, time DESC);
CREATE INDEX idx_telemetry_device_time ON sensor_telemetry (device_id, time DESC);

-- ตั้งค่าการบีบอัดข้อมูล (Compression Policy) เพื่อประหยัดพื้นที่ Storage ได้ถึง 90%
ALTER TABLE sensor_telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tenant_id, zone_id, device_id',
    timescaledb.compress_orderby = 'time DESC'
);
-- บีบอัดข้อมูลเก่าที่เกิน 14 วันอัตโนมัติ
SELECT add_compression_policy('sensor_telemetry', INTERVAL '14 days');

-- ลบข้อมูลดิบเก่าเกิน 365 วัน (หรือเก็บเฉพาะ Continuous Aggregates)
SELECT add_retention_policy('sensor_telemetry', INTERVAL '365 days');

-- ==============================================================================
-- 6.2 TimescaleDB Continuous Aggregates: ค่าเฉลี่ยรายชั่วโมง (Hourly View)
-- ใช้สำหรับวิเคราะห์ความชื้นสะสมโรค Sigatoka, คำนวณ ET0 และแสดงกราฟรายวันอย่างรวดเร็ว
-- ==============================================================================
CREATE MATERIALIZED VIEW sensor_telemetry_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    tenant_id,
    zone_id,
    AVG(soil_moisture_pct) AS avg_soil_moisture,
    MIN(soil_moisture_pct) AS min_soil_moisture,
    MAX(soil_moisture_pct) AS max_soil_moisture,
    AVG(soil_ec_ds_m) AS avg_soil_ec,
    MAX(soil_ec_ds_m) AS max_soil_ec,
    AVG(soil_k_mg_kg) AS avg_soil_k,
    AVG(air_temp_c) AS avg_air_temp,
    MAX(air_temp_c) AS max_air_temp,
    MIN(air_temp_c) AS min_air_temp,
    AVG(air_rh_pct) AS avg_air_rh,
    MAX(wind_speed_kmh) AS max_wind_speed,
    AVG(light_lux) AS avg_light_lux,
    SUM(rain_rate_mm_h) AS total_rain_mm
FROM sensor_telemetry
GROUP BY bucket, tenant_id, zone_id
WITH NO DATA;

-- ตั้ง Refresh Policy ให้รวบรวมข้อมูลทุก 30 นาที
SELECT add_continuous_aggregate_policy('sensor_telemetry_hourly',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');

-- ==============================================================================
-- 7. Actuator & Fertigation Execution History (บันทึกการรดน้ำและให้ปุ๋ย)
-- ==============================================================================
CREATE TABLE fertigation_logs (
    time TIMESTAMPTZ NOT NULL,
    tenant_id UUID NOT NULL,
    zone_id UUID NOT NULL,
    device_id UUID NOT NULL,
    actuator_id UUID REFERENCES actuators(id) ON DELETE SET NULL,
    trigger_type trigger_type_enum NOT NULL,
    growth_stage banana_growth_stage_enum NOT NULL,
    action_type VARCHAR(50) NOT NULL,                             -- 'IRRIGATION_ONLY', 'FERTIGATION_K', 'FERTIGATION_NPK'
    duration_seconds INT NOT NULL,                                -- ระยะเวลาเปิดวาล์ว/ปั๊ม (วินาที)
    water_volume_liters NUMERIC(8, 2) DEFAULT 0.0,                -- ปริมาตรน้ำที่จ่ายไป (ลิตร)
    fertilizer_type VARCHAR(100),                                 -- เช่น '0-0-60 (White Potash)', '13-13-21'
    fertilizer_grams NUMERIC(7, 2) DEFAULT 0.0,
    pre_soil_moisture NUMERIC(5, 2),
    post_soil_moisture NUMERIC(5, 2),
    pre_soil_ec NUMERIC(5, 3),
    post_soil_ec NUMERIC(5, 3),
    notes TEXT
);

SELECT create_hypertable('fertigation_logs', 'time', chunk_time_interval => INTERVAL '30 days');
CREATE INDEX idx_fertigation_tenant_zone_time ON fertigation_logs (tenant_id, zone_id, time DESC);

-- ==============================================================================
-- 8. Automation Rules Engine (Configuration per Zone)
-- รองรับโหมด Classical Rule-Based (โหมด 1: ไม่พึ่งพา AI)
-- ==============================================================================
CREATE TABLE zone_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    zone_id UUID UNIQUE NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    
    -- กฎควบคุมความชื้น (Field Capacity thresholds)
    moisture_trigger_min_pct NUMERIC(5, 2) DEFAULT 70.0 NOT NULL, -- ต่ำกว่านี้เปิดน้ำ
    moisture_cutoff_max_pct NUMERIC(5, 2) DEFAULT 80.0 NOT NULL,  -- สูงถึงนี้สั่งปิดน้ำ
    irrigation_burst_mins INT DEFAULT 15 NOT NULL,                 -- รอบการรดน้ำครั้งละกี่นาที
    irrigation_cooldown_mins INT DEFAULT 45 NOT NULL,              -- พักซึมน้ำก่อนวัดซ้ำกี่นาที
    
    -- กฎความปลอดภัยทางสรีรวิทยา (Kluai Hom Thong Physiological Safety Guard)
    max_safe_ec_ds_m NUMERIC(4, 2) DEFAULT 0.85 NOT NULL,         -- ขีดจำกัด EC สูงสุด (เกินนี้ห้ามจ่ายปุ๋ยเด็ดขาด)
    ec_hard_cutoff_ds_m NUMERIC(4, 2) DEFAULT 1.00 NOT NULL,      -- EC อันตรายวิกฤต (เปิดน้ำล้างเกลือ Flush ทันที)
    wind_cutoff_kmh NUMERIC(4, 1) DEFAULT 30.0 NOT NULL,          -- ลมเกิน 30 km/h สั่งปิดสปริงเกลอร์ (ละอองปลิว/ลมแรง)
    
    -- ปุ๋ยโพแทสเซียม (K) Target สำหรับระยะ 3
    target_k_ppm NUMERIC(6, 2) DEFAULT 250.0,
    fertigation_days_interval INT DEFAULT 7,                       -- รอบให้ปุ๋ยทุกกี่วัน
    
    -- Timer Fallback (กรณีเซนเซอร์ชำรุด)
    schedule_cron_irrigation VARCHAR(50) DEFAULT '0 7,16 * * *',   -- รดน้ำเช้า 07:00 และเย็น 16:00
    is_auto_irrigation_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    is_auto_fertigation_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- ==============================================================================
-- 9. AI Phenotyping & Vision Logs (รองรับโหมด 2: AI-Assisted)
-- วิเคราะห์รูปถ่ายต้นกล้วยหอมทอง ประเมินระยะการเจริญเติบโต และอาการขาดธาตุ/โรค
-- ==============================================================================
CREATE TABLE ai_plant_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    image_url TEXT NOT NULL,                                       -- ลิงก์รูปถ่ายต้นกล้วย (S3 / Cloud Storage)
    
    -- ผลการทำนายทางกายภาพ (Visual Phenotyping)
    predicted_growth_stage banana_growth_stage_enum NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,                       -- ค่าความแม่นยำ 0.0000 - 1.0000
    estimated_age_days INT,
    pseudostem_girth_est_cm NUMERIC(5, 2),                         -- ขนาดเส้นผ่านศูนย์กลางลำต้นเทียม (ซม.)
    active_leaves_count INT,                                       -- จำนวนใบสมบูรณ์ (เป้าหมาย 25-30 ใบ ก่อนแทงปลี)
    bunch_detected BOOLEAN DEFAULT FALSE,                          -- พบเครือกล้วยแล้วหรือไม่
    fruit_angularity_status VARCHAR(50),                           -- 'HIGH_ANGULAR' (ยังมีเหลี่ยมชัด), 'ROUNDING' (เริ่มกลม), 'FULL_ROUND' (ผลกลมพร้อมตัด)
    
    -- การประเมินสุขภาพและโรค
    fusarium_risk_level VARCHAR(20) DEFAULT 'LOW',                 -- 'LOW', 'MEDIUM', 'HIGH'
    sigatoka_leaf_spot_detected BOOLEAN DEFAULT FALSE,
    potassium_deficiency_detected BOOLEAN DEFAULT FALSE,           -- ขอบใบเหลืองไหม้ อาการขาด K
    
    -- คำแนะนำการให้น้ำและปุ๋ยเฉพาะบุคคล (Prescription Fertigation)
    recommended_et0_water_lpd NUMERIC(6, 2),                       -- ปริมาณน้ำแนะนำ (ลิตร/ต้น/วัน)
    recommended_fertilizer_formula VARCHAR(100),                   -- เช่น 'สูตร 0-0-60 เสริม 50 กรัม/ต้น'
    ai_explanation_th TEXT,                                        -- คำอธิบายภาษาไทยสำหรับแสดงใน LINE LIFF
    
    -- Farmer Validation (เกษตรกรกดกดยืนยันใน LINE)
    farmer_confirmed_stage banana_growth_stage_enum,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_ai_assessments_tenant_zone ON ai_plant_assessments(tenant_id, zone_id, created_at DESC);

-- ==============================================================================
-- 10. Alerts & Incident Management (การแจ้งเตือนและการเตือนภัยล่วงหน้า)
-- ==============================================================================
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    farm_id UUID NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    zone_id UUID REFERENCES zones(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    severity alert_severity_enum NOT NULL,
    alert_type alert_type_enum NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    suggested_action TEXT,                                         -- คำแนะนำการแก้ไขทันที
    line_notified BOOLEAN DEFAULT FALSE NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_alerts_tenant_active ON alerts(tenant_id, is_resolved, created_at DESC);

-- ==============================================================================
-- 11. Initial Seed Data (ตัวอย่างการสร้าง Tenant และค่าเริ่มต้น)
-- ==============================================================================
INSERT INTO tenants (id, name, slug, tier, max_farms, max_devices)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'ฟาร์มกล้วยหอมทอง พรีเมียม (Demo Tenant)',
    'homthong-demo',
    'PRO_AI',
    5,
    20
) ON CONFLICT DO NOTHING;
