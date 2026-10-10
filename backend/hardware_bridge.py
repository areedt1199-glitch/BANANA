import serial
import struct
import time
import httpx
from datetime import datetime, timezone

# -------------------------------------------------------------
# Configuration
# -------------------------------------------------------------
COM_PORT = 'COM4'
BAUD_RATE = 4800
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

def read_modbus_7in1(ser):
    """
    Query standard 7 registers from address 0x0000:
    0: Moisture (% / 10)
    1: Temp (C / 10)
    2: EC (us/cm or ms/cm)
    3: pH (/ 10)
    4: N (mg/kg)
    5: P (mg/kg)
    6: K (mg/kg)
    """
    payload = struct.pack('>BBHH', 1, 3, 0, 7)
    frame = payload + calc_crc(payload)
    ser.reset_input_buffer()
    ser.write(frame)
    time.sleep(0.12)
    resp = ser.read(32)
    
    if len(resp) >= 19 and resp[1] == 3:
        data = resp[3:17]
        vals = struct.unpack('>7H', data)
        return {
            "soil_moisture_pct": round(vals[0] / 10.0, 1),
            "soil_temp_c": round(vals[1] / 10.0, 1),
            "soil_ec_ds_m": round(vals[2] / 1000.0, 3) if vals[2] < 5000 else round(vals[2] / 100.0, 3),
            "soil_ph": round(vals[3] / 10.0, 1) if vals[3] > 0 else 6.5,
            "soil_n_mg_kg": float(vals[4]),
            "soil_p_mg_kg": float(vals[5]),
            "soil_k_mg_kg": float(vals[6])
        }
    return None

def fetch_live_microclimate():
    """
    Fetch real-time microclimate (Air Temp, RH, Wind, Solar Radiation) for Pathum Thani
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=14.02&longitude=100.53&current=temperature_2m,relative_humidity_2m,direct_radiation,wind_speed_10m"
        r = httpx.get(url, timeout=3.0)
        curr = r.json().get('current', {})
        air_temp = curr.get('temperature_2m', 29.5)
        air_rh = curr.get('relative_humidity_2m', 75.0)
        solar = curr.get('direct_radiation', 350.0)
        wind = curr.get('wind_speed_10m', 8.5)
        lux = round(solar * 126.7, 1) # Approximate Lux from solar W/m2
        return {
            "air_temp_c": air_temp,
            "air_rh_pct": air_rh,
            "light_lux": max(500.0, lux),
            "solar_radiation_w_m2": solar,
            "wind_speed_kmh": wind
        }
    except Exception:
        return {
            "air_temp_c": 30.5,
            "air_rh_pct": 74.0,
            "light_lux": 42000.0,
            "solar_radiation_w_m2": 330.0,
            "wind_speed_kmh": 10.2
        }

def run_bridge():
    print("=" * 70)
    print("🍌 SMART BANANA IOT - LIVE HARDWARE BRIDGE (COM4)")
    print(f"Connecting to physical RS485 sensor on {COM_PORT} at {BAUD_RATE} baud...")
    print("Pushing live data to: " + BACKEND_URL)
    print("=" * 70)

    try:
        ser = serial.Serial(COM_PORT, baudrate=BAUD_RATE, timeout=0.8)
    except Exception as e:
        print(f"🚨 ไม่สามารถเปิดพอร์ต {COM_PORT} ได้: {e}")
        return

    # Microclimate cache (update every 60s)
    last_weather_time = 0
    cached_weather = fetch_live_microclimate()

    while True:
        try:
            # 1. Update weather every 60s
            if time.time() - last_weather_time > 60:
                cached_weather = fetch_live_microclimate()
                last_weather_time = time.time()

            # 2. Read physical soil sensor on COM4
            soil = read_modbus_7in1(ser)
            if not soil:
                print("⏳ กำลังรอสัญญาณข้อมูลจากเซนเซอร์บน COM4...")
                time.sleep(2)
                continue

            # 3. Combine with microclimate
            payload = {
                "tenant_id": TENANT_ID,
                "zone_id": ZONE_ID,
                "device_id": DEVICE_ID,
                "time": datetime.now(timezone.utc).isoformat(),
                **soil,
                **cached_weather,
                "battery_voltage": 4.15,
                "wifi_rssi_dbm": -60
            }

            # 4. Push to FastAPI Backend
            try:
                res = httpx.post(BACKEND_URL, json=payload, timeout=3.0)
                if res.status_code == 200:
                    r_json = res.json()
                    now_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{now_str}] 🌿 ดินจริง COM4: ชื้น={soil['soil_moisture_pct']}% | EC={soil['soil_ec_ds_m']:.3f} dS/m | K={soil['soil_k_mg_kg']} ppm | อุณหภูมิดิน={soil['soil_temp_c']}°C")
                    print(f"         ☀️ อากาศ & แสง: อุณหภูมิ={cached_weather['air_temp_c']}°C | RH={cached_weather['air_rh_pct']}% | แสง={cached_weather['light_lux']} Lux | ลม={cached_weather['wind_speed_kmh']} km/h")
                    
                    if r_json.get('alerts_triggered'):
                        for a in r_json['alerts_triggered']:
                            print(f"         🚨 แจ้งเตือน: {a['title']}")
                    if r_json.get('actions_taken'):
                        for act in r_json['actions_taken']:
                            print(f"         ⚙️ คำสั่งปั๊ม: {act['command']} -> {act['reason']}")
                else:
                    print(f"Backend HTTP {res.status_code}: {res.text}")
            except Exception as ex:
                print(f"⚠️ ไม่สามารถส่งเข้า Backend ได้ (กรุณารัน run_server.bat): {ex}")

            time.sleep(2.5) # Poll every 2.5s

        except KeyboardInterrupt:
            print("\nปิดการทำงานของ Hardware Bridge เรียบร้อยแล้ว")
            break
        except Exception as e:
            print(f"Error reading sensor: {e}")
            time.sleep(2)

    ser.close()

if __name__ == '__main__':
    run_bridge()
