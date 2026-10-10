import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class BananaTelemetrySimulator:
    """
    Virtual Hardware-in-the-Loop (HIL) Simulator
    Generates realistic Modbus RS485 7-in-1 Soil and Microclimate Telemetry
    for Kluai Hom Thong (กล้วยหอมทอง) plantations.
    Allows testing full frontend, backend, and rule-engine workflows
    before physical hardware is plugged in.
    """

    def __init__(self):
        # Base internal state
        self.moisture_pct = 74.5
        self.ec_ds_m = 0.58
        self.ph = 6.2
        self.n_ppm = 85.0
        self.p_ppm = 42.0
        self.k_ppm = 265.0
        self.soil_temp_c = 28.5
        self.air_temp_c = 31.0
        self.air_rh_pct = 72.0
        self.light_lux = 45000.0
        self.solar_rad_w_m2 = 620.0
        self.wind_speed_kmh = 12.5

    def step(
        self,
        irrigation_active: bool = False,
        dosing_k_active: bool = False,
        scenario: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Advance one simulation step
        """
        if scenario == "HIGH_WIND":
            self.wind_speed_kmh = round(random.uniform(32.0, 42.0), 1)
        else:
            self.wind_speed_kmh = round(random.uniform(8.0, 22.0), 1)

        if scenario == "HIGH_SALINITY":
            self.ec_ds_m = round(random.uniform(1.05, 1.35), 3)
        elif dosing_k_active:
            self.ec_ds_m = min(0.95, round(self.ec_ds_m + 0.05, 3))
            self.k_ppm = min(400.0, round(self.k_ppm + 15.0, 1))
        elif irrigation_active:
            # Flushing effect
            self.ec_ds_m = max(0.35, round(self.ec_ds_m - 0.02, 3))
        else:
            self.ec_ds_m = round(max(0.2, min(0.85, self.ec_ds_m + random.uniform(-0.01, 0.01))), 3)

        if irrigation_active:
            self.moisture_pct = min(85.0, round(self.moisture_pct + random.uniform(1.5, 3.0), 1))
        else:
            # Natural drying out (evapotranspiration)
            decay = 0.2 if scenario != "DROUGHT_STRESS" else 1.2
            self.moisture_pct = max(45.0, round(self.moisture_pct - decay + random.uniform(-0.05, 0.05), 1))

        # Ambient weather fluctuation
        self.air_temp_c = round(random.uniform(28.0, 34.5), 1)
        self.soil_temp_c = round(self.air_temp_c - 2.5 + random.uniform(-0.5, 0.5), 1)
        self.air_rh_pct = round(random.uniform(65.0, 88.0), 1)
        self.light_lux = round(random.uniform(35000.0, 75000.0), 1)
        self.solar_rad_w_m2 = round(self.light_lux * 0.0079, 1)

        return {
            "time": datetime.now(timezone.utc).isoformat(),
            # Modbus 7-in-1 Soil Sensor
            "soil_moisture_pct": self.moisture_pct,
            "soil_temp_c": self.soil_temp_c,
            "soil_ec_ds_m": self.ec_ds_m,
            "soil_ph": self.ph,
            "soil_n_mg_kg": self.n_ppm,
            "soil_p_mg_kg": self.p_ppm,
            "soil_k_mg_kg": self.k_ppm,
            # Weather & Light
            "air_temp_c": self.air_temp_c,
            "air_rh_pct": self.air_rh_pct,
            "light_lux": self.light_lux,
            "solar_radiation_w_m2": self.solar_rad_w_m2,
            "wind_speed_kmh": self.wind_speed_kmh,
            "rain_rate_mm_h": 0.0,
            # Diagnostics
            "battery_voltage": 4.15,
            "wifi_rssi_dbm": random.randint(-68, -55)
        }

simulator_instance = BananaTelemetrySimulator()
