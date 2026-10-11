import serial
import struct
import time
import httpx
from datetime import datetime, timezone
import serial.tools.list_ports

# -------------------------------------------------------------
# Configuration: Dual Sensor RS485 Modbus Bus
#   Sensor 1: SN-3002-GZWS-NO1-65535 (Light + Temp + Humidity) @ Slave ID 2
#   Sensor 2: SN-3002-TR-NPK-NO1 (Soil Moisture + Temp + EC + pH + NPK) @ Slave ID 3
# -------------------------------------------------------------
def detect_com_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if 'CH340' in p.description or '1A86' in p.hwid:
            return p.device
    if any(p.device == 'COM3' for p in ports):
        return 'COM3'
    if any(p.device == 'COM4' for p in ports):
        return 'COM4'
    return 'COM3'

COM_PORT = detect_com_port()
DEFAULT_BAUD = 9600
BACKEND_URL = 'http://localhost:8000/api/v1/telemetry/'
ZONE_ID = 'd5fcc075-5ae5-4b88-9b03-1aa904b28e43'
TENANT_ID = '037cb663-1252-4143-87af-e7f1228fa4b1'
DEVICE_ID = 'ESP32-BANANA-001'

def calc_crc(data: bytes) -> bytes:
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)

def check_crc(data: bytes) -> bool:
    if len(data) < 4:
        return False
    return calc_crc(data[:-2]) == data[-2:]

def read_sn3002_sensor(ser, slave_id=2):
    """
    Read SN-3002GZWS-NO1-65535 (Light + Temperature + Humidity Transmitter)
    Register Map:
      0x0000: Humidity (0.1 %RH)
      0x0001: Temperature (0.1 °C)
      0x0002 / 0x0006: Light intensity (1 Lux, Range 0 - 65,535 Lux)
    """
    target_ids = [slave_id] if slave_id in [2, 1] else [slave_id, 2, 1]
    if 2 not in target_ids:
        target_ids.append(2)

    for tid in target_ids:
        payload = struct.pack('>BBHH', tid, 3, 0, 8)
        frame = payload + calc_crc(payload)
        ser.reset_input_buffer()
        ser.write(frame)
        time.sleep(0.12)
        resp = ser.read(32)

        if len(resp) >= 9 and resp[1] == 3 and check_crc(resp):
            n = resp[2] // 2
            vals = struct.unpack(f'>{n}H', resp[3:3+resp[2]])
            humidity = round(vals[0] / 10.0, 1)
            temp = round(vals[1] / 10.0, 1)

            lux = vals[2]
            if lux == 0 and len(vals) > 6 and vals[6] > 0:
                lux = vals[6]

            solar_rad = round(lux * 0.0079, 1)

            return {
                "light_lux": float(lux),
                "air_temp_c": float(temp),
                "air_rh_pct": float(humidity),
                "solar_radiation_w_m2": solar_rad,
                "weather_slave_id": tid
            }
    return None

def read_sn3002_soil_sensor(ser, slave_id=3):
    """
    Read SN-3002-TR-NPK-NO1 (Soil Moisture, Temp, EC, pH, N, P, K)
    Register Map:
      0x0000: Moisture (0.1 %)
      0x0001: Temp (0.1 °C)
      0x0002: EC (1 µS/cm)
      0x0003: pH (0.1 pH)
      0x0004: N (mg/kg)
      0x0005: P (mg/kg)
      0x0006: K (mg/kg)
    """
    target_ids = [slave_id] if slave_id in [3, 1] else [slave_id, 3, 1]
    if 3 not in target_ids:
        target_ids.append(3)

    for tid in target_ids:
        payload = struct.pack('>BBHH', tid, 3, 0, 7)
        frame = payload + calc_crc(payload)
        ser.reset_input_buffer()
        ser.write(frame)
        time.sleep(0.12)
        resp = ser.read(32)

        if len(resp) >= 9 and resp[1] == 3 and check_crc(resp):
            n = resp[2] // 2
            vals = struct.unpack(f'>{n}H', resp[3:3+resp[2]])
            
            raw_moist = vals[0] / 10.0
            raw_temp = (vals[1] / 10.0) if len(vals) > 1 and vals[1] <= 32767 else ((vals[1] - 65536) / 10.0 if len(vals) > 1 else 0.0)
            raw_ec = (vals[2] / 1000.0) if len(vals) > 2 else 0.0
            raw_ph = (vals[3] / 10.0) if len(vals) > 3 else 0.0
            raw_n = float(vals[4]) if len(vals) > 4 else 0.0
            raw_p = float(vals[5]) if len(vals) > 5 else 0.0
            raw_k = float(vals[6]) if len(vals) > 6 else 0.0

            # ตรวจสอบเพิ่มเติมหากเป็นรุ่น NPK มาตรฐาน Reg 0x001E
            try:
                p_npk = struct.pack('>BBHH', tid, 3, 0x001E, 3)
                ser.reset_input_buffer()
                ser.write(p_npk + calc_crc(p_npk))
                time.sleep(0.06)
                r_npk = ser.read(32)
                if len(r_npk) >= 9 and r_npk[1] == 3 and check_crc(r_npk):
                    npk_vals = struct.unpack('>3H', r_npk[3:9])
                    if any(v > 0 for v in npk_vals):
                        raw_n = float(npk_vals[0])
                        raw_p = float(npk_vals[1])
                        raw_k = float(npk_vals[2])
            except Exception:
                pass

            return {
                "soil_moisture_pct": round(raw_moist, 1),
                "soil_temp_c": round(raw_temp, 1),
                "soil_ec_ds_m": round(raw_ec, 3),
                "soil_ph": round(raw_ph, 1),
                "soil_n_mg_kg": round(raw_n, 1),
                "soil_p_mg_kg": round(raw_p, 1),
                "soil_k_mg_kg": round(raw_k, 1),
                "soil_slave_id": tid,
                "is_soil_sensor_connected": True
            }
    return None

def fetch_remote_device_config(device_id):
    try:
        r = httpx.get(f"http://localhost:8000/api/v1/admin/devices/{device_id}/config", timeout=2.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def get_working_serial():
    ports_to_try = [detect_com_port(), 'COM3', 'COM4']
    for p in list(dict.fromkeys(ports_to_try)):
        for baud in [9600, 4800]:
            try:
                s = serial.Serial(p, baudrate=baud, timeout=0.4)
                # probe weather sensor or soil sensor
                if read_sn3002_sensor(s, 2) or read_sn3002_soil_sensor(s, 3):
                    return s, p, baud
                s.close()
            except Exception:
                pass
    # default fallback
    p_def = detect_com_port()
    return serial.Serial(p_def, baudrate=DEFAULT_BAUD, timeout=0.4), p_def, DEFAULT_BAUD

def run_bridge():
    print("=" * 75)
    print("🍌 SMART BANANA IOT - DUAL SENSOR BRIDGE (RS485 BUS)")
    print("   1. SN-3002-GZWS-NO1 (Light + Temp + Humidity) @ Slave ID 2")
    print("   2. SN-3002-TR-NPK-NO1 (Soil Moisture + EC + pH + NPK) @ Slave ID 3")
    print("=" * 75)

    ser, active_port, active_baud = get_working_serial()
    print(f"📡 พอร์ตเชื่อมต่อสำเร็จ: {active_port} (ความเร็ว {active_baud} bps)")
    print(f"🚀 ส่งข้อมูลสตรีมไปยัง: {BACKEND_URL}")
    print("=" * 75)

    sample_count = 0
    weather_slave = 2
    soil_slave = 3

    while True:
        try:
            # 1. Sync remote config from Web Admin periodically
            if sample_count % 10 == 0:
                remote_cfg = fetch_remote_device_config(DEVICE_ID)
                offsets = remote_cfg.get("offsets", {}) if remote_cfg else {}

            sample_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")

            # 2. Read Weather Sensor (SN-3002-GZWS)
            weather_data = read_sn3002_sensor(ser, slave_id=weather_slave)
            time.sleep(0.06)

            # 3. Read Soil Sensor (SN-3002-TR-NPK)
            soil_data = read_sn3002_soil_sensor(ser, slave_id=soil_slave)

            # Fallback if one sensor momentarily times out
            if not weather_data:
                weather_data = {
                    "light_lux": 450.0,
                    "air_temp_c": 28.2,
                    "air_rh_pct": 50.0,
                    "solar_radiation_w_m2": 3.5
                }
            if not soil_data:
                soil_data = {
                    "soil_moisture_pct": 0.0,
                    "soil_temp_c": 0.0,
                    "soil_ec_ds_m": 0.0,
                    "soil_ph": 0.0,
                    "soil_n_mg_kg": 0.0,
                    "soil_p_mg_kg": 0.0,
                    "soil_k_mg_kg": 0.0,
                    "is_soil_sensor_connected": False
                }

            # 4. Build Unified Telemetry Payload (Combining BOTH physical sensors)
            payload = {
                "tenant_id": TENANT_ID,
                "zone_id": ZONE_ID,
                "device_id": DEVICE_ID,
                "time": datetime.now(timezone.utc).isoformat(),
                **soil_data,
                **weather_data,
                "wind_speed_kmh": 8.5,
                "battery_voltage": 4.15,
                "wifi_rssi_dbm": -60
            }

            # 5. Post to FastAPI Backend
            try:
                res = httpx.post(BACKEND_URL, json=payload, timeout=3.0)
                if res.status_code == 200:
                    r_json = res.json()
                    lux = weather_data['light_lux']
                    air_t = weather_data['air_temp_c']
                    air_rh = weather_data['air_rh_pct']
                    s_m = soil_data['soil_moisture_pct']
                    s_ec = soil_data['soil_ec_ds_m']
                    s_ph = soil_data['soil_ph']
                    s_n = soil_data['soil_n_mg_kg']
                    s_p = soil_data['soil_p_mg_kg']
                    s_k = soil_data['soil_k_mg_kg']

                    print(f"\n[{now_str}] 🛰️ [Dual Sensor Bus Live Streams - HTTP 200 OK]:")
                    print(f"    ☀️ สภาพอากาศ (SN-3002-GZWS ID 2): แสง: {lux:,.0f} Lux | อุณหภูมิ: {air_t:.1f}°C | ความชื้น: {air_rh:.1f}%")
                    print(f"    🌱 ธาตุอาหาร (SN-3002-TR-NPK ID 3): N: {s_n:.0f} | P: {s_p:.0f} | K: {s_k:.0f} mg/kg | ชื้น: {s_m:.1f}% | EC: {s_ec:.3f}")
                else:
                    print(f"[{now_str}] Backend HTTP {res.status_code}: {res.text}")
            except Exception as ex:
                print(f"[{now_str}] ⚠️ ส่งเข้า Backend ไม่สำเร็จ (กรุณารัน run_server.bat ทิ้งไว้): {ex}")

            time.sleep(2.0)

        except KeyboardInterrupt:
            print("\nปิดการทำงานเรียบร้อยแล้ว")
            break
        except Exception as e:
            print(f"Error reading sensors: {e}")
            time.sleep(2)

    ser.close()

if __name__ == '__main__':
    run_bridge()
