import math
from typing import Dict, Any

class BananaET0Calculator:
    """
    FAO-56 Penman-Monteith / Hargreaves Crop Evapotranspiration Calculator
    Specialized for Kluai Hom Thong (กล้วยหอมทอง)
    """

    # Kluai Hom Thong Crop Coefficients (Kc) by Growth Stage
    KC_MAP = {
        "STAGE_1_VEGETATIVE": 0.55,    # ระยะสร้างต้น-สะสมใบ (ทรงพุ่มยังเล็ก)
        "STAGE_2_FLOWERING_BUD": 0.90, # ระยะแทงปลีและติดผล (ห้ามขาดน้ำเด็ดขาด)
        "STAGE_3_FRUIT_BULKING": 1.20, # ระยะเบ่งผลทำน้ำหนัก (คายน้ำสูงสุด ต้องการน้ำคงที่เพื่อขยายเซลล์ผล)
        "STAGE_4_PRE_HARVEST": 0.60    # ก่อนตัด 2-3 สัปดาห์ (ลดน้ำเพื่อให้เนื้อแน่นหวาน ไม่ฉ่ำน้ำ)
    }

    @staticmethod
    def calculate_et0_simple(
        temp_c: float,
        rh_pct: float,
        wind_kmh: float,
        solar_rad_w_m2: float = 0.0
    ) -> float:
        """
        Estimate Daily Reference Evapotranspiration (ET0) in mm/day
        """
        # Wind conversion from km/h to m/s
        u2 = max(0.5, wind_kmh / 3.6)
        
        # Saturation vapor pressure (es) and actual vapor pressure (ea)
        es = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
        ea = es * (rh_pct / 100.0)
        vpd = max(0.0, es - ea) # Vapor Pressure Deficit (kPa)
        
        # Radiation component (approximate net radiation Rn in MJ/m2/day if solar rad given)
        if solar_rad_w_m2 > 10.0:
            # 1 W/m2 ≈ 0.0864 MJ/m2/day
            rn_mj = solar_rad_w_m2 * 0.0864 * 0.77
        else:
            # Estimated clear-sky baseline for tropical Thailand (~16-20 MJ/m2/day)
            rn_mj = 18.0
            
        # Slope of saturation vapor pressure curve (Delta)
        delta = (4098 * es) / ((temp_c + 237.3) ** 2)
        gamma = 0.067 # Psychrometric constant (kPa/°C)
        
        # FAO-56 Penman-Monteith formulation
        numerator = (0.408 * delta * rn_mj) + (gamma * (900 / (temp_c + 273)) * u2 * vpd)
        denominator = delta + (gamma * (1 + 0.34 * u2))
        et0 = max(1.5, min(8.5, numerator / denominator))
        return round(et0, 2)

    @classmethod
    def calculate_daily_irrigation(
        cls,
        growth_stage: str,
        temp_c: float,
        rh_pct: float,
        wind_kmh: float,
        solar_rad_w_m2: float = 0.0,
        canopy_area_sqm: float = 4.0,       # พื้นที่ทรงพุ่มกล้วยหอมทอง ~3.5 - 4.5 ตร.ม./ต้น
        emitter_flow_rate_lph: float = 70.0, # มินิสปริงเกลอร์ 70 ลิตร/ชม./ต้น
        irrigation_efficiency: float = 0.85  # ประสิทธิภาพระบบสปริงเกลอร์ 85%
    ) -> Dict[str, Any]:
        """
        Calculate precise water requirement per tree per day (Liters/tree/day)
        and runtime in minutes for mini-sprinklers.
        """
        et0 = cls.calculate_et0_simple(temp_c, rh_pct, wind_kmh, solar_rad_w_m2)
        kc = cls.KC_MAP.get(growth_stage, 0.90)
        etc = et0 * kc # Crop Evapotranspiration (mm/day)
        
        # Water volume: 1 mm depth on 1 sq.m = 1 Liter
        gross_water_liters = (etc * canopy_area_sqm) / irrigation_efficiency
        
        # In Stage 4 (pre-harvest), intentionally reduce or stop irrigation
        if growth_stage == "STAGE_4_PRE_HARVEST":
            gross_water_liters = gross_water_liters * 0.5
            
        runtime_minutes = (gross_water_liters / emitter_flow_rate_lph) * 60.0
        
        return {
            "et0_mm_day": et0,
            "crop_coefficient_kc": kc,
            "etc_mm_day": round(etc, 2),
            "water_liters_per_tree": round(gross_water_liters, 2),
            "recommended_runtime_minutes": max(5, round(runtime_minutes)),
            "emitter_flow_rate_lph": emitter_flow_rate_lph
        }
