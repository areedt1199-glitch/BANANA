#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🍌 ตัวทดสอบเซนเซอร์วัดแสง อุณหภูมิ ความชื้นอากาศ (SN-3002GZWS-NO1-65535)
สำหรับทดสอบอ่านค่าสดบน COM3 / COM4
"""
import sys
import time
import struct
import serial
import serial.tools.list_ports

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

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

def read_sn3002(ser, slave_id=1):
    payload = struct.pack('>BBHH', slave_id, 3, 0, 8)
    frame = payload + calc_crc(payload)
    ser.reset_input_buffer()
    ser.write(frame)
    time.sleep(0.15)
    resp = ser.read(ser.in_waiting or 32)
    
    if len(resp) >= 9 and resp[1] == 3:
        n = resp[2] // 2
        vals = struct.unpack(f'>{n}H', resp[3:3+resp[2]])
        humidity = round(vals[0] / 10.0, 1)
        temp = round(vals[1] / 10.0, 1)
        lux = vals[2]
        if lux == 0 and len(vals) > 6 and vals[6] > 0:
            lux = vals[6]
        return {
            "humidity": humidity,
            "temp": temp,
            "lux": lux,
            "raw": resp.hex(' ').upper()
        }
    return None

def main():
    print("=" * 65)
    print("🍌 SMART BANANA IOT - ตัวทดสอบเซนเซอร์วัดแสง SN-3002GZWS")
    print("=" * 65)

    ports = [p.device for p in serial.tools.list_ports.comports()]
    default_port = "COM4" if "COM4" in ports else ("COM3" if "COM3" in ports else (ports[0] if ports else "COM4"))
    
    print(f"พอร์ต USB ที่พบ: {ports}")
    user_port = input(f"ระบุพอร์ตที่ใช้งาน [กด Enter ใช้ {default_port}]: ").strip().upper()
    port = user_port if user_port else default_port

    # Auto detect baudrate
    active_baud = None
    ser = None
    print(f"\n📡 กำลังตรวจสอบความเร็ว Baudrate บนพอร์ต {port}...")
    for test_b in [9600, 4800, 19200, 2400]:
        try:
            s_try = serial.Serial(port, baudrate=test_b, timeout=0.3)
            d_try = read_sn3002(s_try, slave_id=1)
            if d_try:
                active_baud = test_b
                ser = s_try
                break
            s_try.close()
        except Exception:
            pass

    if not ser:
        active_baud = 9600
        try:
            ser = serial.Serial(port, baudrate=active_baud, timeout=0.5)
        except Exception as e:
            print(f"❌ ไม่สามารถเปิดพอร์ต {port} ได้: {e}")
            return

    print(f"✅ เชื่อมต่อสำเร็จที่ความเร็ว: {active_baud} bps\n")

    retry_count = 0
    try:
        while True:
            data = read_sn3002(ser, slave_id=1)
            if data:
                retry_count = 0
                print(f"✅ [อ่านค่าสำเร็จ!] แสง: {data['lux']:>5} Lux | อุณหภูมิ: {data['temp']:>4.1f} °C | ความชื้น: {data['humidity']:>4.1f} %RH  (Hex: {data['raw']})")
            else:
                retry_count += 1
                print(f"⏳ [{retry_count}] รอสัญญาณตอบรับจากเซนเซอร์บน {port}... (0 bytes)", end="\r")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n\nหยุดการทำงานเรียบร้อยครับ")
    finally:
        ser.close()

if __name__ == '__main__':
    main()
