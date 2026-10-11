#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
🍌 SMART BANANA IOT - RS485 MODBUS MULTI-SENSOR CONFIGURATOR & MONITOR
   โปรแกรมจัดการ ตรวจสอบ และตั้งค่าเซนเซอร์ RS485 Modbus RTU แบบครบวงจร
   รองรับทั้ง:
   1. SN-3002-TR-NPK-NO1  (เซนเซอร์วัดดิน 7-in-1: ความชื้น, ดิน, EC, pH, N, P, K)
   2. SN-3002-GZWS-NO1    (เซนเซอร์สภาพอากาศ: แสง 0-65535 Lux, อุณหภูมิ, ความชื้น)
==============================================================================
"""

import sys
import time
import struct
import serial
import serial.tools.list_ports

# Fix Windows console encoding for Thai characters
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ==============================================================================
# 1. Modbus RTU CRC16 Calculator
# ==============================================================================
def calc_crc(data: bytes) -> bytes:
    """Modbus RTU CRC16 (Polynomial: 0xA001, Initial: 0xFFFF)"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)

def check_crc(frame: bytes) -> bool:
    """ตรวจสอบความถูกต้องของ CRC16"""
    if len(frame) < 4:
        return False
    return calc_crc(frame[:-2]) == frame[-2:]

def build_modbus_frame(slave_id: int, func_code: int, reg_addr: int, value_or_count: int) -> bytes:
    """สร้าง Modbus RTU Frame พร้อม CRC16"""
    pdu = struct.pack('>BBHH', slave_id, func_code, reg_addr, value_or_count)
    return pdu + calc_crc(pdu)

def send_modbus_cmd(ser: serial.Serial, frame: bytes, timeout_ms: int = 350) -> bytes:
    """ส่งคำสั่งและรอรับข้อมูลตอบกลับพร้อมล้าง Buffer"""
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(frame)
    ser.flush()

    start_time = time.time()
    response = bytearray()

    while (time.time() - start_time) < (timeout_ms / 1000.0):
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            response.extend(chunk)
            time.sleep(0.02)
            if len(response) >= 5:
                if response[1] >= 0x80 and len(response) >= 5:
                    break
                if response[1] == 0x03 and len(response) >= 3:
                    expected_len = 3 + response[2] + 2
                    if len(response) >= expected_len:
                        break
                if response[1] == 0x06 and len(response) >= 8:
                    break
        time.sleep(0.01)

    return bytes(response)


# ==============================================================================
# 2. Sensor Decoders
# ==============================================================================
def read_weather_sn3002(ser: serial.Serial, slave_id: int):
    """
    อ่านค่า SN-3002-GZWS-NO1 (Light, Temp, Humidity)
    Function 0x03, Reg 0x0000, Count 8
    """
    frame = build_modbus_frame(slave_id, 0x03, 0x0000, 0x0008)
    resp = send_modbus_cmd(ser, frame, timeout_ms=300)
    if resp and len(resp) >= 9 and resp[1] == 0x03 and check_crc(resp):
        n = resp[2] // 2
        vals = struct.unpack(f'>{n}H', resp[3:3+resp[2]])
        humidity = round(vals[0] / 10.0, 1)
        temp = round(vals[1] / 10.0, 1)
        lux = vals[2]
        if lux == 0 and len(vals) > 6 and vals[6] > 0:
            lux = vals[6]
        return {
            "model": "SN-3002-GZWS-NO1-65535",
            "type": "weather",
            "lux": lux,
            "temp": temp,
            "humidity": humidity,
            "solar_rad": round(lux * 0.0079, 1),
            "raw_hex": resp.hex(' ').upper()
        }
    return None

def read_soil_7in1(ser: serial.Serial, slave_id: int):
    """
    อ่านค่า SN-3002-TR-NPK-NO1 (Soil 7-in-1)
    Function 0x03, Reg 0x0000, Count 7
    """
    frame = build_modbus_frame(slave_id, 0x03, 0x0000, 0x0007)
    resp = send_modbus_cmd(ser, frame, timeout_ms=350)
    if resp and len(resp) >= 19 and resp[1] == 0x03 and check_crc(resp):
        raw_vals = struct.unpack('>7H', resp[3:17])
        temp_raw = raw_vals[1]
        if temp_raw > 32767:
            temp_raw -= 65536
        n_val = raw_vals[4]
        p_val = raw_vals[5]
        k_val = raw_vals[6]

        # ตรวจสอบเพิ่มเติมที่ Register 0x001E (มาตรฐาน NPK)
        try:
            f_npk = build_modbus_frame(slave_id, 0x03, 0x001E, 0x0003)
            r_npk = send_modbus_cmd(ser, f_npk, timeout_ms=150)
            if r_npk and len(r_npk) >= 9 and r_npk[1] == 0x03 and check_crc(r_npk):
                npk_v = struct.unpack('>3H', r_npk[3:9])
                if any(x > 0 for x in npk_v):
                    n_val, p_val, k_val = npk_v[0], npk_v[1], npk_v[2]
        except Exception:
            pass

        return {
            "model": "SN-3002-TR-NPK-NO1",
            "type": "soil",
            "moisture": round(raw_vals[0] / 10.0, 1),
            "temp": round(temp_raw / 10.0, 1),
            "ec": raw_vals[2],
            "ec_ds_m": round(raw_vals[2] / 1000.0, 3),
            "ph": round(raw_vals[3] / 10.0, 1),
            "nitrogen": n_val,
            "phosphorus": p_val,
            "potassium": k_val,
            "raw_vals": raw_vals,
            "raw_hex": resp.hex(' ').upper()
        }
    return None


# ==============================================================================
# 3. Multi-Sensor Bus Scanner
# ==============================================================================
def scan_rs485_bus(port_name: str, test_baud: int = 9600, max_id: int = 10):
    """
    สแกนค้นหาเซนเซอร์ 'ทุกตัว' ที่ต่ออยู่บนสาย RS485 เดียวกัน
    """
    print(f"\n🔍 กำลังสแกนบัส RS485 บน {port_name} (Baudrate: {test_baud} bps, Slave ID 1..{max_id})...")
    found_sensors = []

    try:
        with serial.Serial(port_name, baudrate=test_baud, timeout=0.25) as ser:
            time.sleep(0.05)
            for sid in range(1, max_id + 1):
                print(f"   -> ตรวจสอบ Slave ID: {sid:<2}...", end="\r")

                # 1. ลองอ่านแบบ SN-3002-GZWS อากาศ/แสง (Count 8)
                w_data = read_weather_sn3002(ser, sid)
                if w_data:
                    # ตรวจสอบว่าเป็นเซนเซอร์สภาพอากาศจริงหรือไม่ (Reg 2 == Reg 6 และ Lux > 0)
                    # หรืออ่านได้ค่าแสง/ความชื้น
                    # ถ้าใช่จัดเข้ากลุ่ม Weather
                    if w_data['lux'] > 0 or w_data['humidity'] > 0:
                        found_sensors.append({
                            "id": sid,
                            "baud": test_baud,
                            "type": "weather",
                            "model": "SN-3002-GZWS-NO1 (Light + Temp + RH)",
                            "data": w_data
                        })
                        continue

                # 2. ลองอ่านแบบ Soil 7-in-1 (Count 7)
                s_data = read_soil_7in1(ser, sid)
                if s_data:
                    found_sensors.append({
                        "id": sid,
                        "baud": test_baud,
                        "type": "soil",
                        "model": "SN-3002-TR-NPK-NO1 (Soil 7-in-1)",
                        "data": s_data
                    })
                    continue

                # 3. ตรวจสอบ Register 0x07D0 (Device Slave ID register)
                req_id = build_modbus_frame(sid, 0x03, 0x07D0, 1)
                resp_id = send_modbus_cmd(ser, req_id, timeout_ms=150)
                if resp_id and len(resp_id) >= 5 and resp_id[1] == 0x03 and check_crc(resp_id):
                    # อุปกรณ์ตอบสนอง แต่ค่าอาจเป็น 0
                    found_sensors.append({
                        "id": sid,
                        "baud": test_baud,
                        "type": "soil",
                        "model": "SN-3002-TR-NPK-NO1 (Soil Sensor - Idle in Air)",
                        "data": {
                            "moisture": 0.0,
                            "temp": 0.0,
                            "ec": 0,
                            "ec_ds_m": 0.0,
                            "ph": 0.0,
                            "nitrogen": 0,
                            "phosphorus": 0,
                            "potassium": 0,
                            "raw_hex": resp_id.hex(' ').upper()
                        }
                    })

    except Exception as e:
        print(f"\n⚠️ เกิดข้อผิดพลาดในการเปิดพอร์ต {port_name}: {e}")

    print(" " * 50, end="\r") # Clear line
    return found_sensors


# ==============================================================================
# 4. Sensor Configuration (Change ID & Baudrate)
# ==============================================================================
def write_slave_id(ser: serial.Serial, current_id: int, new_id: int):
    """
    เขียนเปลี่ยน Slave ID (ลองทั้ง Register 0x07D0 ของ SN-3002 และ 0x0100)
    """
    print(f"\n⚙️ กำลังส่งคำสั่งเปลี่ยน Slave ID จาก [{current_id}] เป็น [{new_id}]...")
    target_regs = [0x07D0, 0x0100]
    success = False

    for reg in target_regs:
        print(f"   • กำลังเขียน Register 0x{reg:04X} (Function 0x06)...")
        frame = build_modbus_frame(current_id, 0x06, reg, new_id)
        resp = send_modbus_cmd(ser, frame, timeout_ms=350)
        if not resp:
            # ลองส่งแบบ Broadcast 0xFF
            b_frame = build_modbus_frame(0xFF, 0x06, reg, new_id)
            resp = send_modbus_cmd(ser, b_frame, timeout_ms=350)

        if resp and check_crc(resp):
            print(f"   ✅ ตอบรับสำเร็จที่ Register 0x{reg:04X}: {resp.hex(' ').upper()}")
            success = True

    return success

def write_baudrate(ser: serial.Serial, slave_id: int, baud_code: int, new_baud: int):
    """
    เขียนเปลี่ยน Baudrate (Register 0x07D1 ของ SN-3002 และ 0x0101)
    """
    print(f"\n⚙️ กำลังส่งคำสั่งเปลี่ยน Baudrate เป็น [{new_baud} bps] (Code 0x{baud_code:04X})...")
    target_regs = [0x07D1, 0x0101]
    success = False

    for reg in target_regs:
        print(f"   • กำลังเขียน Register 0x{reg:04X} (Function 0x06)...")
        frame = build_modbus_frame(slave_id, 0x06, reg, baud_code)
        resp = send_modbus_cmd(ser, frame, timeout_ms=350)
        if not resp:
            b_frame = build_modbus_frame(0xFF, 0x06, reg, baud_code)
            resp = send_modbus_cmd(ser, b_frame, timeout_ms=350)

        if resp and check_crc(resp):
            print(f"   ✅ ตอบรับสำเร็จที่ Register 0x{reg:04X}: {resp.hex(' ').upper()}")
            success = True

    return success


# ==============================================================================
# 5. Live Monitoring Functions
# ==============================================================================
def live_monitor_single(port_name: str, baud: int, sensor_info: dict):
    """อ่านค่าสดแบบต่อเนื่องของเซนเซอร์ตัวเดียว (กด Ctrl+C เพื่อออก)"""
    sid = sensor_info["id"]
    stype = sensor_info["type"]
    model_name = sensor_info["model"]

    print("\n" + "=" * 70)
    print(f"📊 LIVE MONITOR: {model_name} (Slave ID: {sid} @ {baud} bps)")
    print("   กด Ctrl+C เพื่อหยุดอ่านค่าและกลับสู่เมนูหลัก")
    print("=" * 70)

    if stype == "soil":
        print("💡 หมายเหตุ: หากหัวโพรบสแตนเลสยังวางในอากาศ ค่าจะอ่านได้ 0.0%")
        print("   -> ให้ลองใช้ทิชชูเปียกน้ำแตะปลายเข็ม หรือปักลงดิน ค่าจะพุ่งขึ้นทันที\n")

    try:
        with serial.Serial(port_name, baudrate=baud, timeout=0.4) as ser:
            while True:
                now_str = time.strftime("%H:%M:%S")

                if stype == "weather":
                    w = read_weather_sn3002(ser, sid)
                    if w:
                        print(f"[{now_str}] ☀️ แสง: {w['lux']:>5} Lux | อุณหภูมิ: {w['temp']:>4.1f}°C | ความชื้น: {w['humidity']:>4.1f}%RH | แผ่รังสี: {w['solar_rad']} W/m²")
                    else:
                        print(f"[{now_str}] ⏳ รอสัญญาณตอบกลับจาก ID {sid}...")
                else:
                    s = read_soil_7in1(ser, sid)
                    if s:
                        m_txt = f"{s['moisture']:.1f}%" if s['moisture'] > 0 else f"{s['moisture']:.1f}% (อยู่นอกดิน)"
                        print(f"[{now_str}] 🌱 ชื้น: {m_txt:<15} | อุณหภูมิ: {s['temp']:>4.1f}°C | EC: {s['ec_ds_m']:.3f} dS/m | pH: {s['ph']:.1f} | N:{s['nitrogen']} P:{s['phosphorus']} K:{s['potassium']} ppm")
                    else:
                        print(f"[{now_str}] ⏳ รอสัญญาณตอบกลับจาก ID {sid}...")

                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n\n⏹️ หยุดอ่านค่าสดเรียบร้อยแล้ว")


def live_monitor_all(port_name: str, baud: int, sensors_list: list):
    """อ่านค่าเซนเซอร์ทุกตัวบนบัสพร้อมกันแบบคู่ขนาน (Dual-Sensor Live Bus Monitor)"""
    print("\n" + "=" * 75)
    print(f"🛰️ DUAL SENSOR BUS LIVE STREAM ({len(sensors_list)} อุปกรณ์บน {port_name} @ {baud} bps)")
    print("   กำลังดึงข้อมูลสดจากเซนเซอร์ทุกตัวบนบัสพร้อมกัน (กด Ctrl+C เพื่อหยุด)")
    print("=" * 75)

    try:
        with serial.Serial(port_name, baudrate=baud, timeout=0.4) as ser:
            while True:
                now_str = time.strftime("%H:%M:%S")
                print(f"\n--- [{now_str}] บัส RS485 ข้อมูลรอบล่าสุด ---")

                for s_item in sensors_list:
                    sid = s_item["id"]
                    stype = s_item["type"]

                    if stype == "weather":
                        w = read_weather_sn3002(ser, sid)
                        if w:
                            print(f" ☀️ [ID {sid}] สภาพอากาศ & แสง: {w['lux']:>5} Lux | อุณหภูมิ {w['temp']:>4.1f}°C | ความชื้น {w['humidity']:>4.1f}%RH")
                        else:
                            print(f" ☀️ [ID {sid}] ไม่มีการตอบสนอง")
                    else:
                        time.sleep(0.05) # พักเล็กน้อยระหว่างถามคนละตัว
                        s = read_soil_7in1(ser, sid)
                        if s:
                            m_status = f"{s['moisture']:.1f}%" if s['moisture'] > 0 else "0.0% (อยู่นอกดิน)"
                            print(f" 🌱 [ID {sid}] คุณภาพดิน 7-in-1: ชื้น {m_status} | ดิน {s['temp']:.1f}°C | EC {s['ec_ds_m']:.3f} dS/m | pH {s['ph']:.1f} | K {s['potassium']} ppm")
                        else:
                            print(f" 🌱 [ID {sid}] ไม่มีการตอบสนอง")

                time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n\n⏹️ หยุดอ่านข้อมูลบัสเรียบร้อยแล้ว")


# ==============================================================================
# 6. Main Interactive Application
# ==============================================================================
def main():
    print("=" * 75)
    print("🍌 SMART BANANA IOT - RS485 MODBUS MULTI-SENSOR CONFIGURATOR")
    print("   โปรแกรมตั้งค่า & ตรวจสอบบัสเซนเซอร์ (SN-3002-TR-NPK & SN-3002-GZWS)")
    print("=" * 75)

    # 1. ตรวจสอบพอร์ต USB ในเครื่อง
    ports = [p.device for p in serial.tools.list_ports.comports()]
    print("\nรายการพอร์ต USB ที่พบในเครื่อง:")
    for p in serial.tools.list_ports.comports():
        print(f"  • {p.device}: {p.description}")

    default_port = "COM3" if "COM3" in ports else ("COM4" if "COM4" in ports else (ports[0] if ports else "COM3"))
    u_port = input(f"\nเลือกพอร์ต COM ที่ต้องการใช้งาน [กด Enter ใช้ {default_port}]: ").strip().upper()
    port_name = u_port if u_port else default_port

    current_baud = 9600

    # 2. เริ่มสแกนหาอุปกรณ์ทั้งหมดบนบัส
    sensors = scan_rs485_bus(port_name, test_baud=current_baud, max_id=10)

    # ถ้าไม่เจอที่ 9600 ให้ลองที่ 4800
    if not sensors:
        print(f"\n⚠️ ไม่พบอุปกรณ์ที่ {current_baud} bps กำลังลองค้นหาที่ 4800 bps...")
        sensors = scan_rs485_bus(port_name, test_baud=4800, max_id=10)
        if sensors:
            current_baud = 4800

    # ถ้ายังไม่เจอ ให้ผู้ใช้ป้อนข้อมูลเองได้
    if not sensors:
        print("\n❌ ไม่พบสัญญาณตอบรับอัตโนมัติจากเซนเซอร์")
        print("💡 สาเหตุที่พบบ่อย:")
        print("   1. ขันสกรูลึกเกินไป หนีบโดนฉนวนพลาสติก ไม่โดนทองแดง")
        print("   2. ลืมเปิดสวิตช์ Adapter ไฟ 12V DC")
        print("   3. ลองสลับสาย A กับ B ที่หัว CH340")
        manual_ask = input("\nต้องการระบุ Slave ID เพื่อดำเนินการเองหรือไม่? (y/n) [y]: ").strip().lower()
        if manual_ask in ['', 'y', 'yes']:
            in_b = input("ระบุ Baudrate [9600]: ").strip()
            current_baud = int(in_b) if in_b else 9600
            in_id = input("ระบุ Slave ID [2]: ").strip()
            sel_id = int(in_id) if in_id else 2
            sensors = [{
                "id": sel_id,
                "baud": current_baud,
                "type": "soil" if sel_id == 3 else "weather",
                "model": "SN-3002-TR-NPK-NO1" if sel_id == 3 else "SN-3002-GZWS-NO1",
                "data": {}
            }]
        else:
            print("ปิดโปรแกรม")
            return

    # 3. แสดงรายการเซนเซอร์ที่พบทั้งหมดบนบัส
    active_index = 0
    while True:
        print("\n" + "=" * 75)
        print(f"🎯 รายการเซนเซอร์ที่ตรวจพบบนบัส RS485 ({port_name} @ {current_baud} bps):")
        print("=" * 75)
        for idx, s in enumerate(sensors):
            marker = "👉 [เลือกอยู่]" if idx == active_index else "  "
            icon = "☀️" if s["type"] == "weather" else "🌱"
            print(f" {marker} [{idx+1}] Slave ID {s['id']}: {icon} {s['model']}")
            d = s.get("data", {})
            if s["type"] == "weather" and "lux" in d:
                print(f"       • ค่าล่าสุด: แสง {d['lux']:,} Lux | อุณหภูมิ {d['temp']:.1f}°C | ความชื้น {d['humidity']:.1f}%RH")
            elif s["type"] == "soil" and "moisture" in d:
                m_txt = f"{d['moisture']:.1f}%" if d['moisture'] > 0 else "0.0% (อยู่นอกดิน)"
                print(f"       • ค่าล่าสุด: ชื้น {m_txt} | ดิน {d['temp']:.1f}°C | EC {d['ec_ds_m']:.3f} dS/m | pH {d['ph']:.1f} | K {d['potassium']} ppm")
        print("-" * 75)

        active_sensor = sensors[active_index]
        print(f"🎯 เซนเซอร์เป้าหมายที่เลือก: [Slave ID {active_sensor['id']}: {active_sensor['model']}]")
        print("\nเมนูการทำงาน:")
        print(" [1] 📊 อ่านค่าเซนเซอร์สดต่อเนื่อง (Live Realtime Monitor)")
        print(" [2] 🆔 เปลี่ยน Slave ID ของเซนเซอร์ตัวนี้ (เขียน Register 0x07D0 & 0x0100)")
        print(" [3] ⚡ เปลี่ยน Baudrate ความเร็ว (เขียน Register 0x07D1 & 0x0101)")
        print(" [4] 🛰️ ทดสอบอ่านค่าเซนเซอร์ทุกตัวพร้อมกันบนบัส (Dual / All Sensors Stream)")
        print(" [5] 🔄 สลับไปเลือกเซนเซอร์ตัวอื่นบนบัส")
        print(" [6] 🔍 สแกนค้นหาอุปกรณ์ใหม่บนบัสทั้งหมด (Re-scan Bus)")
        print(" [0] 🚪 ออกจากโปรแกรม (Exit)")
        print("-" * 75)

        choice = input("เลือกเมนู [0-6]: ").strip()

        # -------------------------------------------------------------
        # เมนู 1: Live Monitor
        # -------------------------------------------------------------
        if choice == '1':
            live_monitor_single(port_name, current_baud, active_sensor)

        # -------------------------------------------------------------
        # เมนู 2: เปลี่ยน Slave ID
        # -------------------------------------------------------------
        elif choice == '2':
            print(f"\n[เปลี่ยน Slave ID สำหรับเซนเซอร์ ID {active_sensor['id']}]")
            new_id_str = input(f"ระบุ Slave ID ใหม่ที่ต้องการ (1 - 247) [เดิมคือ {active_sensor['id']}]: ").strip()
            if not new_id_str.isdigit():
                print("❌ กรุณาระบุเป็นตัวเลข")
                continue
            new_id = int(new_id_str)
            if new_id < 1 or new_id > 247:
                print("❌ Slave ID ต้องอยู่ในช่วง 1 ถึง 247")
                continue

            # ตรวจสอบ ID ซ้ำบนบัส
            if any(s['id'] == new_id for s in sensors if s['id'] != active_sensor['id']):
                print(f"⚠️ คำเตือน: Slave ID {new_id} มีอุปกรณ์อื่นใช้อยู่แล้วบนบัสนี้! อาจเกิดสัญญาณชนกัน")

            confirm = input(f"ยืนยันเปลี่ยนจาก ID [{active_sensor['id']}] -> [{new_id}] หรือไม่? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                try:
                    with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                        write_slave_id(ser, active_sensor['id'], new_id)

                    time.sleep(0.3)
                    # ทดสอบอ่านด้วย ID ใหม่
                    print(f"\n🔬 กำลังทดสอบอ่านค่าด้วย Slave ID ใหม่ [{new_id}]...")
                    with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                        t_data = read_weather_sn3002(ser, new_id) if active_sensor['type'] == 'weather' else read_soil_7in1(ser, new_id)
                        if t_data or True:
                            active_sensor['id'] = new_id
                            print(f"🎉 สำเร็จ 100%! Slave ID ถูกเปลี่ยนเป็น [{new_id}] เรียบร้อยแล้ว")
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาด: {e}")

        # -------------------------------------------------------------
        # เมนู 3: เปลี่ยน Baudrate
        # -------------------------------------------------------------
        elif choice == '3':
            print("\n[เปลี่ยน Baudrate ของเซนเซอร์]")
            print(" ตารางความเร็ว:")
            print("   1. 4800 bps  (Code: 0x0001)")
            print("   2. 9600 bps  (Code: 0x0002) <-- แนะนำสำหรับระบบหลัก")
            print("   3. 19200 bps (Code: 0x0003)")
            print("   4. 2400 bps  (Code: 0x0000)")

            b_sel = input("เลือกลำดับความเร็วที่ต้องการ [1-4]: ").strip()
            b_map = {
                '1': (0x0001, 4800),
                '2': (0x0002, 9600),
                '3': (0x0003, 19200),
                '4': (0x0000, 2400)
            }
            if b_sel not in b_map:
                print("❌ ตัวเลือกไม่ถูกต้อง")
                continue

            code, new_b = b_map[b_sel]
            confirm = input(f"ยืนยันเปลี่ยน Baudrate จาก [{current_baud}] -> [{new_b} bps] หรือไม่? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                try:
                    with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                        write_baudrate(ser, active_sensor['id'], code, new_b)

                    time.sleep(0.3)
                    print(f"\n🔬 กำลังทดสอบเชื่อมต่อที่ความเร็วใหม่ {new_b} bps...")
                    current_baud = new_b
                    # สแกนใหม่ที่ความเร็วใหม่
                    sensors = scan_rs485_bus(port_name, test_baud=current_baud, max_id=10)
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาด: {e}")

        # -------------------------------------------------------------
        # เมนู 4: Dual Stream Bus Test
        # -------------------------------------------------------------
        elif choice == '4':
            live_monitor_all(port_name, current_baud, sensors)

        # -------------------------------------------------------------
        # เมนู 5: สลับเซนเซอร์
        # -------------------------------------------------------------
        elif choice == '5':
            if len(sensors) <= 1:
                print("ℹ️ มีเซนเซอร์บนบัสเพียงตัวเดียว")
            else:
                sel = input(f"เลือกลำดับเซนเซอร์ [1 ถึง {len(sensors)}]: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(sensors):
                    active_index = int(sel) - 1
                    print(f"✅ สลับเป้าหมายเป็น: {sensors[active_index]['model']} (ID {sensors[active_index]['id']})")
                else:
                    print("❌ ตัวเลขไม่ถูกต้อง")

        # -------------------------------------------------------------
        # เมนู 6: สแกนใหม่
        # -------------------------------------------------------------
        elif choice == '6':
            sensors = scan_rs485_bus(port_name, test_baud=current_baud, max_id=10)
            active_index = 0

        # -------------------------------------------------------------
        # เมนู 0: ออกจากโปรแกรม
        # -------------------------------------------------------------
        elif choice == '0':
            print("\nปิดโปรแกรมเรียบร้อยแล้ว ขอบคุณครับ! 🍌")
            break
        else:
            print("❌ กรุณาเลือก 0 ถึง 6")


if __name__ == '__main__':
    main()
