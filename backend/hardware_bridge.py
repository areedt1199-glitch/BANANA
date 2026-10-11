import serial
import struct
import time
import httpx
from datetime import datetime, timezone

import serial.tools.list_ports

# -------------------------------------------------------------
# Configuration: SN-3002GZWS-NO1-65535
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

def get_working_serial(port_name):
    for baud in [9600, 4800, 19200, 2400]:
        try:
            s = serial.Serial(port_name, baudrate=baud, timeout=0.5)
            # test probe
            test_data = read_sn3002_sensor(s)
            if test_data:
                return s, baud
            s.close()
        except Exception:
            pass
    # default fallback
    return serial.Serial(port_name, baudrate=DEFAULT_BAUD, timeout=0.5), DEFAULT_BAUD

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

def read_sn3002_sensor(ser, slave_id=2):
    """
    Read SN-3002GZWS-NO1-65535 (Light + Temperature + Humidity Transmitter)
    Register Map:
      0x0000: Humidity (0.1 %RH)
      0x0001: Temperature (0.1 °C)
      0x0002 / 0x0006: Light intensity (1 Lux, Range 0 - 65,535 Lux)
    """
    # Check configured slave_id first, then fallback to 2, 1, 255
    target_ids = [slave_id] if slave_id in [1, 2] else [slave_id, 2, 1]
    if 2 not in target_ids:
        target_ids.append(2)
    if 1 not in target_ids:
        target_ids.append(1)

    for tid in target_ids:
        payload = struct.pack('>BBHH', tid, 3, 0, 8)
        frame = payload + calc_crc(payload)
        ser.reset_input_buffer()
        ser.write(frame)
        time.sleep(0.12)
        resp = ser.read(32)

        if len(resp) >= 9 and resp[1] == 3:
            n = resp[2] // 2
            vals = struct.unpack(f'>{n}H', resp[3:3+resp[2]])
            humidity = round(vals[0] / 10.0, 1)
            temp = round(vals[1] / 10.0, 1)

            # Light Lux from Register 2 (or 6 if 2 is 0)
            lux = vals[2]
            if lux == 0 and len(vals) > 6 and vals[6] > 0:
                lux = vals[6]

            solar_rad = round(lux * 0.0079, 1) # Approximate W/m2 from Lux

            return {
                "light_lux": float(lux),
                "air_temp_c": float(temp),
                "air_rh_pct": float(humidity),
                "solar_radiation_w_m2": solar_rad
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

def run_bridge():
    print("=" * 70)
    # 1. Sync remote config from Web Admin
    remote_cfg = fetch_remote_device_config(DEVICE_ID)
    if remote_cfg:
        print(f"☁️ ซิงก์การตั้งค่าจาก Web Admin สำเร็จ: อุปกรณ์ {DEVICE_ID} (ฟาร์ม {remote_cfg.get('farm_id')[:8]})")
        print(f"   • รุ่นเซนเซอร์: {remote_cfg.get('sensor_model')} | ความเร็ว: {remote_cfg.get('baud_rate')} bps")
        print(f"   • ความถี่อ่านค่า: {remote_cfg.get('telemetry_interval_sec')} วินาที")
    
    ser, active_baud = get_working_serial(COM_PORT)
    print(f"📡 พอร์ตเชื่อมต่อ: {COM_PORT} (ตรวจพบความเร็ว {active_baud} bps)")
    print("💡 วัดค่าจริงจากเซนเซอร์: ค่าแสง (Lux), อุณหภูมิอากาศ (°C), ความชื้นอากาศ (%RH)")
    print(f"🚀 ส่งข้อมูลสตรีมไปยัง: {BACKEND_URL}")
    print("=" * 70)

    # Baseline soil profile for Kluai Hom Thong plantation (since soil probe is separate)
    soil_profile = {
        "soil_moisture_pct": 74.8,
        "soil_temp_c": 28.5,
        "soil_ec_ds_m": 0.580,
        "soil_ph": 6.2,
        "soil_n_mg_kg": 85.0,
        "soil_p_mg_kg": 42.0,
        "soil_k_mg_kg": 265.0
    }

    sample_count = 0

    while True:
        try:
            # Re-sync offsets and slave_id periodically
            if sample_count % 10 == 0:
                remote_cfg = fetch_remote_device_config(DEVICE_ID)
                offsets = remote_cfg.get("offsets", {}) if remote_cfg else {}
                current_slave_id = remote_cfg.get("modbus_slave_id", 2) if remote_cfg else 2

            # 1. Read real sensor SN-3002GZWS from COM4
            sensor_data = read_sn3002_sensor(ser, slave_id=current_slave_id)
            if not sensor_data:
                print("⏳ กำลังรอสัญญาณข้อมูลจากเซนเซอร์ SN-3002GZWS บน COM4...")
                time.sleep(2)
                continue

            sample_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")

            # 2. Build Unified Telemetry Payload
            payload = {
                "tenant_id": TENANT_ID,
                "zone_id": ZONE_ID,
                "device_id": DEVICE_ID,
                "time": datetime.now(timezone.utc).isoformat(),
                **soil_profile,
                **sensor_data,
                "wind_speed_kmh": 8.5,
                "battery_voltage": 4.15,
                "wifi_rssi_dbm": -60
            }

            # 3. Post to FastAPI Backend
            try:
                res = httpx.post(BACKEND_URL, json=payload, timeout=3.0)
                if res.status_code == 200:
                    r_json = res.json()
                    lux_val = sensor_data['light_lux']
                    temp_val = sensor_data['air_temp_c']
                    rh_val = sensor_data['air_rh_pct']

                    print(f"\n[{now_str}] ☀️ เซนเซอร์จริง SN-3002GZWS (COM4):")
                    print(f"    💡 แสงแดด:       {lux_val:,.0f} Lux (0 - 65,535 Lux)")
                    print(f"    🌡️ อุณหภูมิอากาศ: {temp_val:.1f} °C")
                    print(f"    💧 ความชื้นอากาศ: {rh_val:.1f} %RH")
                    print(f"    🌱 ดินกล้วยหอมทอง: ชื้น {soil_profile['soil_moisture_pct']}% | EC {soil_profile['soil_ec_ds_m']:.2f} dS/m | K {soil_profile['soil_k_mg_kg']:.0f} ppm")
                    print(f"    -> อัปเดตขึ้น Web Admin & LINE LIFF สำเร็จ (HTTP 200 OK)")

                    if r_json.get('alerts_triggered'):
                        for a in r_json['alerts_triggered']:
                            print(f"    🚨 แจ้งเตือน: {a['title']}")
                else:
                    print(f"Backend HTTP {res.status_code}: {res.text}")
            except Exception as ex:
                print(f"⚠️ ส่งเข้า Backend ไม่สำเร็จ (กรุณารัน run_server.bat ทิ้งไว้): {ex}")

            time.sleep(2.0) # Read every 2 seconds

        except KeyboardInterrupt:
            print("\nปิดการทำงานเรียบร้อยแล้ว")
            break
        except Exception as e:
            print(f"Error reading sensor: {e}")
            time.sleep(2)

    ser.close()

if __name__ == '__main__':
    run_bridge()
