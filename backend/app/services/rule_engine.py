from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.models.entities import (
    Zone, ZoneRule, SensorTelemetry, Actuator, Alert, AlertSeverity, AlertType, TriggerType, BananaGrowthStage
)
from app.core.config import settings

class RuleEngineResult:
    def __init__(self):
        self.actions: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self.logs: List[str] = []

class ClassicalRuleEngine:
    """
    Mode 1: Classical Deterministic Rule-Based Engine
    Works independently without AI, with zero Cloud AI cost and maximum reliability.
    Enforces critical Kluai Hom Thong agronomic safety rules.
    """

    @staticmethod
    def evaluate(
        zone: Zone,
        rule: ZoneRule,
        telemetry: SensorTelemetry,
        actuators: List[Actuator]
    ) -> RuleEngineResult:
        result = RuleEngineResult()
        
        # -------------------------------------------------------------
        # 1. HARD SAFETY GUARD #1: Salinity / Electrical Conductivity (EC)
        # กล้วยหอมทองทนเค็มต่ำมาก: EC > 0.85 dS/m ต้องหยุดปุ๋ย, EC >= 1.0 อันตรายรากไหม้
        # -------------------------------------------------------------
        if telemetry.soil_ec_ds_m is not None:
            if telemetry.soil_ec_ds_m >= rule.ec_hard_cutoff_ds_m:
                result.alerts.append({
                    "severity": AlertSeverity.CRITICAL.value,
                    "alert_type": AlertType.HIGH_EC_SALINITY.value,
                    "title": f"🚨 วิกฤตค่าความเค็ม EC สูงเกินเกณฑ์ ({telemetry.soil_ec_ds_m:.2f} dS/m)",
                    "message": f"โซน '{zone.name}' ตรวจพบค่า EC ดินสูงแตะขีดอันตรายวิกฤต ({telemetry.soil_ec_ds_m:.2f} dS/m > {rule.ec_hard_cutoff_ds_m:.2f} dS/m) ซึ่งทำให้ระบบรากฝอยกล้วยหอมทองไหม้และชะงักการดูดน้ำทันที!",
                    "suggested_action": "ตัดปั๊มปุ๋ยทุกตัวทันที และเปิดน้ำเปล่าชะล้างเกลือ (Leaching/Flushing) ในดินด่วน"
                })
                # ตัดปั๊มปุ๋ยทันที
                for act in actuators:
                    if "FERTILIZER" in act.actuator_type and act.is_active:
                        result.actions.append({
                            "actuator_id": act.id,
                            "command": "STOP",
                            "reason": "SAFETY_CUTOFF: EC Exceeded Hard Limit"
                        })
                result.logs.append(f"Safety Cutoff: High EC detected ({telemetry.soil_ec_ds_m} dS/m). Fertilizer pumps killed.")

            elif telemetry.soil_ec_ds_m >= rule.max_safe_ec_ds_m:
                result.alerts.append({
                    "severity": AlertSeverity.WARNING.value,
                    "alert_type": AlertType.HIGH_EC_SALINITY.value,
                    "title": f"⚠️ แจ้งเตือนค่า EC เริ่มสูง ({telemetry.soil_ec_ds_m:.2f} dS/m)",
                    "message": f"โซน '{zone.name}' ค่า EC ในดินใกล้ถึงขีดจำกัดความปลอดภัย ({rule.max_safe_ec_ds_m:.2f} dS/m)",
                    "suggested_action": "ชะลอการจ่ายปุ๋ย และให้น้ำเปล่าเพื่อควบคุมความเข้มข้นสารละลายในดิน"
                })

        # -------------------------------------------------------------
        # 2. HARD SAFETY GUARD #2: Wind Speed Hazard (>30 km/h)
        # ลำต้นเทียมไม่มีเนื้อไม้แท้ และเครือกล้วยหนัก เสี่ยงต้นหักโค่น
        # -------------------------------------------------------------
        if telemetry.wind_speed_kmh is not None and telemetry.wind_speed_kmh >= rule.wind_cutoff_kmh:
            result.alerts.append({
                "severity": AlertSeverity.CRITICAL.value,
                "alert_type": AlertType.HIGH_WIND_COLLAPSE.value,
                "title": f"🌪️ เตือนภัยลมกระโชกแรง ({telemetry.wind_speed_kmh:.1f} km/h)",
                "message": f"ความเร็วลมในแปลงแตะ {telemetry.wind_speed_kmh:.1f} km/h เกินเกณฑ์ปลอดภัย ({rule.wind_cutoff_kmh:.1f} km/h) เสี่ยงต้นกล้วยหอมทองหักโค่นโดยเฉพาะต้นที่มีเครือ!",
                "suggested_action": "เข้าตรวจแปลง ค้ำยันลำต้นด้วยไม้ไผ่หรือเชือกโยง 3 ทิศทางทันที และปิดสปริงเกลอร์ชั่วคราวเพื่อป้องกันละอองน้ำปลิว"
            })
            # ปิดวาล์วน้ำขณะลมแรง
            for act in actuators:
                if act.actuator_type == "VALVE_IRRIGATION" and act.is_active:
                    result.actions.append({
                        "actuator_id": act.id,
                        "command": "STOP",
                        "reason": "SAFETY_CUTOFF: Extreme Wind Speed"
                    })

        # -------------------------------------------------------------
        # 3. IRRIGATION CONTROL (ความชื้นดินตามเกณฑ์ Field Capacity)
        # -------------------------------------------------------------
        if rule.is_auto_irrigation_enabled and telemetry.soil_moisture_pct is not None:
            # ป้องกันเปิดน้ำถ้าระบบติดเงื่อนไขลมแรงหรือน้ำท่วมขัง
            wind_safe = telemetry.wind_speed_kmh is None or telemetry.wind_speed_kmh < rule.wind_cutoff_kmh

            if telemetry.soil_moisture_pct < rule.moisture_trigger_min_pct and wind_safe:
                # ต่ำกว่าเกณฑ์ขั้นต่ำ -> สั่งเปิดน้ำ
                for act in actuators:
                    if act.actuator_type == "VALVE_IRRIGATION" and not act.is_active:
                        result.actions.append({
                            "actuator_id": act.id,
                            "command": "START",
                            "duration_seconds": rule.irrigation_burst_mins * 60,
                            "reason": f"Soil Moisture ({telemetry.soil_moisture_pct:.1f}%) < Threshold ({rule.moisture_trigger_min_pct:.1f}%)"
                        })
                        result.logs.append(f"Irrigation Triggered: Zone '{zone.name}' low moisture.")

            elif telemetry.soil_moisture_pct >= rule.moisture_cutoff_max_pct:
                # สูงเกินเกณฑ์เพดาน -> สั่งปิดน้ำทันที ป้องกันรากเน่า/Fusarium
                for act in actuators:
                    if act.actuator_type == "VALVE_IRRIGATION" and act.is_active:
                        result.actions.append({
                            "actuator_id": act.id,
                            "command": "STOP",
                            "reason": f"Soil Moisture ({telemetry.soil_moisture_pct:.1f}%) >= Cutoff ({rule.moisture_cutoff_max_pct:.1f}%)"
                        })
                        result.logs.append(f"Irrigation Stopped: Moisture target reached.")

        # -------------------------------------------------------------
        # 4. POTASSIUM FERTIGATION CONTROL (สำหรับระยะ 3: เบ่งผลทำน้ำหนัก)
        # สัดส่วนปุ๋ย K สูง 1:0.5:4 (สูตร 0-0-60 หรือ 13-13-21)
        # -------------------------------------------------------------
        if rule.is_auto_fertigation_enabled and zone.current_stage == BananaGrowthStage.STAGE_3_FRUIT_BULKING.value:
            ec_safe = telemetry.soil_ec_ds_m is not None and telemetry.soil_ec_ds_m < rule.max_safe_ec_ds_m
            k_level = telemetry.soil_k_mg_kg or 0.0

            if k_level < rule.target_k_ppm and ec_safe:
                for act in actuators:
                    if act.actuator_type == "PUMP_FERTILIZER_K" and not act.is_active:
                        result.actions.append({
                            "actuator_id": act.id,
                            "command": "START",
                            "duration_seconds": 300,  # 5 minutes injection
                            "fertilizer_formula": "0-0-60 White Potash (High K)",
                            "reason": f"Stage 3 Fruit Bulking: Potassium {k_level:.1f} ppm < Target {rule.target_k_ppm:.1f} ppm"
                        })
                        result.logs.append(f"K Fertigation Triggered for Stage 3 Fruit Bulking.")

        return result
