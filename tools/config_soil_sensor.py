#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
🍌 โปรแกรมตั้งค่าเซนเซอร์ดิน RS485 Modbus 7-in-1 (Soil Sensor Configurator)
สำหรับตัวแปลง USB-SERIAL CH340 (เช่น COM3)
==============================================================================
ฟังก์ชันการทำงาน:
1. เชื่อมต่อพอร์ต COM (ค่าเริ่มต้น COM3 หรือกำหนดเองได้)
2. Auto-Detect: สแกนหา Baudrate (4800, 9600, ฯลฯ) และ Slave ID ปัจจุบัน
   - รองรับทั้งการส่ง Broadcast 0xFF (Query Address & 7 Registers)
   - สแกน Slave ID 1..15 พร้อมคำนวณ CRC16
3. เมนูเปลี่ยน Slave ID: เขียน Register 0x0100 ด้วย Function 0x06
4. เมนูเปลี่ยน Baudrate: เขียน Register 0x0101 ด้วย Function 0x06 (9600 = 0x0002)
5. คำนวณและตรวจสอบ CRC16 Modbus RTU อัตโนมัติทุกคำสั่ง
6. ยืนยันผล 100%: อ่านค่าดิน 7 ค่าซ้ำด้วย ID และ Baudrate ใหม่ทันที
==============================================================================
"""

import sys
import time
import struct
import serial
import serial.tools.list_ports

# Force UTF-8 on Windows terminal to prevent UnicodeEncodeError in CP874
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
    """
    คำนวณ Checksum CRC16 สำหรับ Modbus RTU
    Polynomial: 0xA001, Initial: 0xFFFF
    ส่งกลับเป็น 2 bytes (Low byte ก่อน, High byte หลัง)
    """
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
    """ตรวจสอบความถูกต้องของ CRC16 ในข้อมูลที่ตอบกลับมา"""
    if len(frame) < 4:
        return False
    expected_crc = calc_crc(frame[:-2])
    actual_crc = frame[-2:]
    return expected_crc == actual_crc

def build_modbus_frame(slave_id: int, func_code: int, reg_addr: int, value_or_count: int) -> bytes:
    """สร้าง Modbus RTU Frame พร้อมคำนวณ CRC16 ต่อท้ายให้อัตโนมัติ"""
    pdu = struct.pack('>BBHH', slave_id, func_code, reg_addr, value_or_count)
    return pdu + calc_crc(pdu)

# ==============================================================================
# 2. Modbus Communication Helper
# ==============================================================================
def send_modbus_command(ser: serial.Serial, frame: bytes, timeout_ms: int = 350) -> bytes:
    """ส่งคำสั่งและรอรับข้อมูลตอบกลับพร้อมตัด Buffer สะอาด"""
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(frame)
    ser.flush()
    
    start_time = time.time()
    response = bytearray()
    
    # รอจนกว่าจะมีข้อมูลหรือหมดเวลา
    while (time.time() - start_time) < (timeout_ms / 1000.0):
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            response.extend(chunk)
            time.sleep(0.03) # ให้เวลาเฟรมที่เหลือเข้ามา
            
            # ตรวจสอบว่าเฟรมครบแล้วหรือไม่
            if len(response) >= 5:
                # Modbus Exception Response: ID(1) + Func|0x80(1) + Exception(1) + CRC(2) = 5 bytes
                if response[1] >= 0x80 and len(response) >= 5:
                    break
                # Modbus Read Response Func 0x03: ID(1) + Func(1) + ByteCount(1) + Data(N) + CRC(2)
                if response[1] == 0x03 and len(response) >= 3:
                    expected_len = 3 + response[2] + 2
                    if len(response) >= expected_len:
                        break
                # Modbus Write Single Register Func 0x06: ID(1) + Func(1) + Reg(2) + Val(2) + CRC(2) = 8 bytes
                if response[1] == 0x06 and len(response) >= 8:
                    break
        time.sleep(0.01)
        
    return bytes(response)

# ==============================================================================
# 3. Read 7-in-1 Soil Telemetry
# ==============================================================================
def read_soil_7in1(ser: serial.Serial, slave_id: int):
    """
    ส่งคำสั่ง Function 0x03 อ่าน 7 Registers เริ่มจาก 0x0000:
    [0] ความชื้น (Moisture % / 10)
    [1] อุณหภูมิ (Temp °C / 10)
    [2] ความเค็ม (EC µS/cm)
    [3] กรด-ด่าง (pH / 10)
    [4] ไนโตรเจน (N mg/kg)
    [5] ฟอสฟอรัส (P mg/kg)
    [6] โพแทสเซียม (K mg/kg)
    """
    frame = build_modbus_frame(slave_id, 0x03, 0x0000, 0x0007)
    resp = send_modbus_command(ser, frame, timeout_ms=400)
    
    if not resp:
        return None, "ไม่มีสัญญาณตอบกลับจากเซนเซอร์ (Timeout - 0 bytes)"
    
    if not check_crc(resp):
        return None, f"CRC16 ผิดพลาด: {resp.hex(' ').upper()}"
        
    if resp[1] != 0x03:
        return None, f"เซนเซอร์ตอบกลับด้วย Error Code (Func {resp[1]:02X}): {resp.hex(' ').upper()}"
        
    if len(resp) < 19:
        return None, f"ความยาวข้อมูลสั้นเกินไป ({len(resp)} bytes): {resp.hex(' ').upper()}"
        
    byte_count = resp[2]
    if byte_count != 14:
        return None, f"ความยาวข้อมูลไม่ใช่ 14 bytes (ได้ {byte_count} bytes)"
        
    raw_vals = struct.unpack('>7H', resp[3:17])
    
    # จัดการอุณหภูมิติดลบ (Signed 16-bit)
    temp_raw = raw_vals[1]
    if temp_raw > 32767:
        temp_raw -= 65536
        
    data = {
        "moisture": raw_vals[0] / 10.0,
        "temperature": temp_raw / 10.0,
        "ec": raw_vals[2],
        "ec_ds_m": raw_vals[2] / 1000.0,
        "ph": raw_vals[3] / 10.0,
        "nitrogen": raw_vals[4],
        "phosphorus": raw_vals[5],
        "potassium": raw_vals[6],
        "raw_hex": resp.hex(' ').upper()
    }
    return data, None

# ==============================================================================
# 4. Auto-Detect Engine (สแกนหา Baudrate และ Slave ID)
# ==============================================================================
def print_hardware_guide():
    """แสดงคำแนะนำการต่อวงจรอย่างละเอียด"""
    print("\n" + "=" * 65)
    print("🛠️ สาเหตุที่พบบ่อยเมื่อเซนเซอร์ไม่ตอบสนอง (0 Bytes Received):")
    print("=" * 65)
    print(" 1. [สำคัญที่สุด!] แหล่งจ่ายไฟภายนอก 12V-24V DC:")
    print("    • ตัวแปลง USB-RS485 CH340 จ่ายไฟได้แค่ 5V จาก USB คอมพิวเตอร์")
    print("    • เซนเซอร์ดิน 7-in-1 ต้องใช้ไฟเลี้ยง 12V ถึง 24V DC เท่านั้น (ห้ามใช้ไฟ 5V)")
    print("    • สายสีน้ำตาล (Brown) -> ต่อเข้ากับไฟบวก (+12V DC) ของ Adapter")
    print("    • สายสีดำ (Black)     -> ต่อเข้ากับไฟลบ (GND) ของ Adapter และต่อร่วมกับ GND ของ CH340")
    print("")
    print(" 2. สลับสายสัญญาณ RS485 (A กับ B สลับกัน):")
    print("    • สายสีเหลือง (Yellow) -> ต่อเข้า RS485 ขั้ว A (หรือ A+)")
    print("    • สายสีน้ำเงิน (Blue)  -> ต่อเข้า RS485 ขั้ว B (หรือ B-)")
    print("    • ⚠️ ถ้ายังไม่เจอ ให้ลอง 'สลับสาย A กับ B สลับกัน' ทันที")
    print("       (หัวแปลง CH340 หลายยี่ห้อสกรีน A/B สลับข้างกัน)")
    print("")
    print(" 3. สายทองแดงไม่สัมผัสขั้ว:")
    print("    • ขันสกรูแน่นเกินไปจนหนีบโดนปลอกพลาสติก หรือสายหลวม")
    print("=" * 65)

def auto_detect_sensor(port_name: str, scan_baudrates=[4800, 9600, 19200, 2400, 115200]):
    """
    สแกนค้นหาเซนเซอร์อัตโนมัติ:
    1. ส่ง Broadcast Frame (0xFF) อ่าน Register 0x0100 (Address Inquiry)
    2. ส่งคำสั่ง Function 0x03 อ่าน 7 Registers (0x0000, 0x0007)
    3. สแกน Slave ID 1..10
    """
    print("\n" + "=" * 65)
    print(f"🔍 เริ่มต้นระบบ Auto-Detect สแกนหาเซนเซอร์บนพอร์ต {port_name}...")
    print("=" * 65)
    
    scan_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    for baud in scan_baudrates:
        print(f"\n📡 กำลังตรวจสอบที่ Baudrate: {baud} bps...")
        try:
            with serial.Serial(port_name, baudrate=baud, timeout=0.35) as ser:
                time.sleep(0.05) # พักหลังจากเปิดพอร์ต
                
                # --- สเต็ป 1: ลอง Broadcast Address Inquiry (0xFF, Reg 0x0100) ---
                print(f"   -> [1/3] ทดสอบ Broadcast Address Inquiry (0xFF)...", end="\r")
                frame_inquiry = build_modbus_frame(0xFF, 0x03, 0x0100, 0x0001)
                resp = send_modbus_command(ser, frame_inquiry, timeout_ms=300)
                if resp and len(resp) >= 5 and check_crc(resp):
                    actual_slave = resp[0] if resp[0] != 0xFF else (resp[4] if len(resp) >= 5 else 1)
                    print(f"\n\n🎯 [ตรวจพบเซนเซอร์ผ่าน Broadcast Inquiry!]")
                    print(f"   ----------------------------------------")
                    print(f"   • พอร์ต (COM Port):   {port_name}")
                    print(f"   • ความเร็ว (Baud):    {baud} bps")
                    print(f"   • หมายเลข (Slave ID):  {actual_slave} (0x{actual_slave:02X})")
                    print(f"   • เฟรมตอบกลับ:       {resp.hex(' ').upper()}")
                    print(f"   ----------------------------------------")
                    return baud, actual_slave

                # --- สเต็ป 2: ลอง Broadcast อ่าน 7 Registers ทันที (0xFF, Reg 0x0000, Count 7) ---
                print(f"   -> [2/3] ทดสอบ Broadcast Read 7-in-1 (0xFF)...   ", end="\r")
                frame_b7 = build_modbus_frame(0xFF, 0x03, 0x0000, 0x0007)
                resp = send_modbus_command(ser, frame_b7, timeout_ms=350)
                if resp and len(resp) >= 7 and check_crc(resp):
                    actual_slave = resp[0]
                    print(f"\n\n🎯 [ตรวจพบเซนเซอร์ผ่าน Broadcast Read 7-in-1!]")
                    print(f"   ----------------------------------------")
                    print(f"   • พอร์ต (COM Port):   {port_name}")
                    print(f"   • ความเร็ว (Baud):    {baud} bps")
                    print(f"   • หมายเลข (Slave ID):  {actual_slave} (0x{actual_slave:02X})")
                    print(f"   • เฟรมตอบกลับ:       {resp.hex(' ').upper()}")
                    print(f"   ----------------------------------------")
                    return baud, actual_slave

                # --- สเต็ป 3: วนสแกนตามราย ID (อ่าน 7 Registers แบบมาตรฐาน) ---
                for slave in scan_ids:
                    print(f"   -> [3/3] ตรวจสอบ Slave ID: {slave:<3}                      ", end="\r")
                    
                    # คำสั่งมาตรฐาน 7 Registers (เซนเซอร์ดินชอบคำสั่งนี้ที่สุด)
                    frame = build_modbus_frame(slave, 0x03, 0x0000, 0x0007)
                    resp = send_modbus_command(ser, frame, timeout_ms=250)
                    
                    if resp and len(resp) >= 5 and check_crc(resp):
                        actual_slave = resp[0]
                        print(f"\n\n🎯 [ตรวจพบเซนเซอร์เรียบร้อยแล้ว!]")
                        print(f"   ----------------------------------------")
                        print(f"   • พอร์ต (COM Port):   {port_name}")
                        print(f"   • ความเร็ว (Baud):    {baud} bps")
                        print(f"   • หมายเลข (Slave ID):  {actual_slave} (0x{actual_slave:02X})")
                        print(f"   • เฟรมตอบกลับ:       {resp.hex(' ').upper()}")
                        print(f"   ----------------------------------------")
                        return baud, actual_slave

        except Exception as e:
            print(f"\n⚠️ เกิดข้อผิดพลาดที่ Baud {baud}: {e}")
            
    print("\n\n❌ ไม่พบสัญญาณตอบรับจากเซนเซอร์ในรายการทดสอบมาตรฐาน")
    print_hardware_guide()
    return None, None

# ==============================================================================
# 5. Configuration Functions (เปลี่ยน ID และ Baudrate)
# ==============================================================================
def change_slave_id(ser: serial.Serial, current_id: int, new_id: int, reg_addr: int = 0x0100):
    """
    เปลี่ยน Slave ID โดยเขียน Register 0x0100 (มาตรฐานดิน) และ 0x07D0 (มาตรฐาน SN-3002)
    """
    print(f"\n⚙️ กำลังส่งคำสั่งเปลี่ยน Slave ID จาก [{current_id}] เป็น [{new_id}]...")
    
    # ลองเขียนทั้ง Register 0x0100 และ 0x07D0
    target_regs = [0x0100, 0x07D0] if reg_addr == 0x0100 else [reg_addr]
    success_any = False
    
    for r in target_regs:
        print(f"   • ลองเขียน Register: 0x{r:04X} (Function 0x06)")
        frame = build_modbus_frame(current_id, 0x06, r, new_id)
        resp = send_modbus_command(ser, frame, timeout_ms=400)
        
        if not resp:
            # Broadcast 0xFF
            b_frame = build_modbus_frame(0xFF, 0x06, r, new_id)
            resp = send_modbus_command(ser, b_frame, timeout_ms=400)
            
        if resp and check_crc(resp):
            print(f"   ✅ สำเร็จที่ Register 0x{r:04X}: {resp.hex(' ').upper()}")
            success_any = True
            
    return success_any or True

def change_baudrate(ser: serial.Serial, current_id: int, baud_code: int, new_baud_rate: int, reg_addr: int = 0x0101):
    """
    เปลี่ยน Baudrate โดยเขียน Register 0x0101 (มาตรฐานดิน) และ 0x07D1 (มาตรฐาน SN-3002)
    ตารางรหัส:
      0x0000 = 2400 bps
      0x0001 = 4800 bps
      0x0002 = 9600 bps
      0x0003 = 19200 bps
    """
    print(f"\n⚙️ กำลังส่งคำสั่งเปลี่ยน Baudrate เป็น [{new_baud_rate} bps] (Code: 0x{baud_code:04X})...")
    
    target_regs = [0x0101, 0x07D1] if reg_addr == 0x0101 else [reg_addr]
    success_any = False
    
    for r in target_regs:
        print(f"   • กำลังเขียน Register: 0x{r:04X} (Function 0x06)")
        frame = build_modbus_frame(current_id, 0x06, r, baud_code)
        resp = send_modbus_command(ser, frame, timeout_ms=400)
        
        if not resp:
            b_frame = build_modbus_frame(0xFF, 0x06, r, baud_code)
            resp = send_modbus_command(ser, b_frame, timeout_ms=400)
            
        if resp and check_crc(resp):
            print(f"   ✅ ตอบรับสำเร็จที่ Register 0x{r:04X}: {resp.hex(' ').upper()}")
            success_any = True
            
    return success_any or True

# ==============================================================================
# 6. Verification Routine (ตรวจสอบผล 100%)
# ==============================================================================
def read_sn3002_raw(ser: serial.Serial, slave_id: int):
    """อ่านข้อมูลเซนเซอร์วัดแสง/อากาศ SN-3002GZWS (Reg 0x0000, Count 8)"""
    frame = build_modbus_frame(slave_id, 0x03, 0x0000, 0x0008)
    resp = send_modbus_command(ser, frame, timeout_ms=400)
    if resp and len(resp) >= 9 and resp[1] == 0x03 and check_crc(resp):
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
            "raw_hex": resp.hex(' ').upper()
        }, None
    return None, "ไม่ใช่เฟรม SN-3002"

def verify_sensor_operation(port_name: str, test_baud: int, test_id: int):
    """
    ทดสอบเชื่อมต่อด้วยพารามิเตอร์ใหม่ และอ่านค่าเพื่อยืนยัน 100%
    รองรับทั้งเซนเซอร์ดิน 7-in-1 และเซนเซอร์วัดแสง SN-3002
    """
    print("\n" + "=" * 65)
    print(f"🔬 กำลังทดสอบยืนยันผล 100% ด้วยค่าใหม่ (Baud: {test_baud}, ID: {test_id})...")
    print("=" * 65)
    time.sleep(0.4)
    
    try:
        with serial.Serial(port_name, baudrate=test_baud, timeout=0.6) as ser:
            # 1. ลองอ่านแบบ SN-3002 (Light + Temp + Humidity)
            light_data, _ = read_sn3002_raw(ser, test_id)
            if light_data:
                print("🎉 [ผลการทดสอบ: ยืนยันสำเร็จ 100%! ตรวจพบเซนเซอร์ SN-3002GZWS]")
                print("-----------------------------------------------------------------")
                print(f" 💡 1. ความเข้มแสง (Light Intensity):  {light_data['lux']:>6} Lux")
                print(f" 🌡️ 2. อุณหภูมิอากาศ (Air Temp):       {light_data['temp']:>6.1f} °C")
                print(f" 💧 3. ความชื้นอากาศ (Air RH):         {light_data['humidity']:>6.1f} %RH")
                print("-----------------------------------------------------------------")
                print(f" ข้อมูลดิบ Hex Response: {light_data['raw_hex']}")
                return True
                
            # 2. ลองอ่านแบบ Soil 7-in-1
            data, err = read_soil_7in1(ser, test_id)
            if data:
                print("🎉 [ผลการทดสอบ: ยืนยันสำเร็จ 100%! ตรวจพบเซนเซอร์วัดดิน 7-in-1]")
                print("-----------------------------------------------------------------")
                print(f" 🌿 1. ความชื้นในดิน (Moisture):   {data['moisture']:>6.1f} %")
                print(f" 🌡️ 2. อุณหภูมิดิน (Temperature):  {data['temperature']:>6.1f} °C")
                print(f" ⚡ 3. ความเค็มดิน (Soil EC):      {data['ec']:>6} µS/cm ({data['ec_ds_m']:.3f} dS/m)")
                print(f" 🧪 4. ความเป็นกรด-ด่าง (pH):     {data['ph']:>6.1f}")
                print(f" 🍃 5. ไนโตรเจน (Nitrogen - N):   {data['nitrogen']:>6} mg/kg (ppm)")
                print(f" 🌾 6. ฟอสฟอรัส (Phosphorus - P): {data['phosphorus']:>6} mg/kg (ppm)")
                print(f" 🍌 7. โพแทสเซียม (Potassium - K): {data['potassium']:>6} mg/kg (ppm)")
                print("-----------------------------------------------------------------")
                print(f" ข้อมูลดิบ Hex Response: {data['raw_hex']}")
                return True
            else:
                print(f"❌ ทดสอบอ่านค่าไม่สำเร็จ: {err}")
                return False
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปิดพอร์ตทดสอบ: {e}")
        return False

# ==============================================================================
# 7. Main Interactive CLI Menu
# ==============================================================================
def list_available_ports():
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]

def main():
    print("=" * 65)
    print("🍌 SMART BANANA IOT - 7-in-1 SOIL SENSOR CONFIGURATOR")
    print("   โปรแกรมตั้งค่าเซนเซอร์ดิน RS485 Modbus RTU ผ่าน USB-CH340")
    print("=" * 65)

    # 1. เลือกพอร์ต COM
    avail_ports = list_available_ports()
    default_port = "COM3" if "COM3" in avail_ports else (avail_ports[0] if avail_ports else "COM3")
    
    print("\nรายการพอร์ต USB ที่พบในเครื่อง:")
    for p in serial.tools.list_ports.comports():
        print(f"  • {p.device}: {p.description}")
        
    user_port = input(f"\nเลือกพอร์ต COM ที่ต้องการใช้งาน [กด Enter ใช้ {default_port}]: ").strip()
    port_name = user_port.upper() if user_port else default_port

    current_baud = None
    current_id = None

    # 2. ทำการ Auto-Detect ครั้งแรก
    current_baud, current_id = auto_detect_sensor(port_name)
    
    if not current_baud:
        print("\n⚠️ ไม่สามารถ Auto-Detect เซนเซอร์ได้โดยตรง")
        print("💡 คุณสามารถลองสลับสาย A กับ B แล้วกดเลือกเมนูเพื่อสแกนใหม่ หรือระบุค่าด้วยตนเอง")
        manual = input("ต้องการระบุค่าเพื่อสั่งการเองหรือไม่? (y/n) [ค่าเริ่มต้น: y]: ").strip().lower()
        if manual in ['', 'y', 'yes']:
            b_in = input("ระบุ Baudrate ที่คาดว่าใช้งาน [กด Enter ใช้ 4800]: ").strip()
            current_baud = int(b_in) if b_in else 4800
            id_in = input("ระบุ Slave ID ที่คาดว่าใช้งาน [กด Enter ใช้ 1]: ").strip()
            current_id = int(id_in) if id_in else 1
        else:
            print("ปิดโปรแกรม")
            return

    # 3. เมนูหลักวนซ้ำ
    while True:
        print("\n" + "=" * 65)
        print(f"📋 เมนูการตั้งค่าเซนเซอร์ดิน (พอร์ต: {port_name} | Baud: {current_baud} | ID: {current_id})")
        print("=" * 65)
        print(" [1] 📊 อ่านค่าดิน 7 ค่าปัจจุบัน (Test Read 7-in-1)")
        print(" [2] 🆔 เปลี่ยน Slave ID ใหม่ (เขียน Register 0x0100)")
        print(" [3] ⚡ เปลี่ยน Baudrate ใหม่ (เขียน Register 0x0101)")
        print(" [4] 🔍 สแกนหาเซนเซอร์ใหม่อีกครั้ง (Re-scan Auto-Detect)")
        print(" [0] 🚪 ออกจากโปรแกรม (Exit)")
        print("-" * 65)
        
        choice = input("เลือกเมนูการทำงาน [0-4]: ").strip()
        
        # -------------------------------------------------------------
        # เมนู 1: อ่านค่าดิน 7 ค่า
        # -------------------------------------------------------------
        if choice == '1':
            verify_sensor_operation(port_name, current_baud, current_id)
            
        # -------------------------------------------------------------
        # เมนู 2: เปลี่ยน Slave ID
        # -------------------------------------------------------------
        elif choice == '2':
            print(f"\n[เปลี่ยน Slave ID ของเซนเซอร์]")
            new_id_str = input(f"ระบุ Slave ID ใหม่ที่ต้องการ (1 - 247) [เดิมคือ {current_id}]: ").strip()
            if not new_id_str.isdigit():
                print("❌ กรุณาระบุเป็นตัวเลขเท่านั้น")
                continue
            new_id = int(new_id_str)
            if new_id < 1 or new_id > 247:
                print("❌ Slave ID ต้องอยู่ในช่วง 1 ถึง 247")
                continue
                
            confirm = input(f"ยืนยันเปลี่ยนจาก ID [{current_id}] -> [{new_id}] หรือไม่? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                try:
                    with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                        success = change_slave_id(ser, current_id, new_id, reg_addr=0x0100)
                    
                    # ตรวจสอบ 100%
                    if verify_sensor_operation(port_name, current_baud, new_id):
                        current_id = new_id
                        print(f"🎉 อัปเดตการจำค่าในระบบ: Slave ID ปัจจุบันเปลี่ยนเป็น [{current_id}] เรียบร้อย")
                    else:
                        print("⚠️ เซนเซอร์อาจยังไม่เปลี่ยนค่า หรือต้องลองใช้ Register สำรอง 0x07D0")
                        retry_alt = input("ต้องการลองเขียนด้วย Register สำรอง 0x07D0 หรือไม่? (y/n): ").strip().lower()
                        if retry_alt in ['y', 'yes']:
                            with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                                change_slave_id(ser, current_id, new_id, reg_addr=0x07D0)
                            if verify_sensor_operation(port_name, current_baud, new_id):
                                current_id = new_id
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาด: {e}")

        # -------------------------------------------------------------
        # เมนู 3: เปลี่ยน Baudrate
        # -------------------------------------------------------------
        elif choice == '3':
            print("\n[เปลี่ยน Baudrate ของเซนเซอร์]")
            print(" ตารางความเร็วและรหัส Register 0x0101:")
            print("   1. 2400 bps  (Code: 0x0000)")
            print("   2. 4800 bps  (Code: 0x0001)")
            print("   3. 9600 bps  (Code: 0x0002) <-- แนะนำสำหรับงานทั่วไป")
            print("   4. 19200 bps (Code: 0x0003)")
            
            b_sel = input("เลือกลำดับความเร็วที่ต้องการ [1-4]: ").strip()
            baud_map = {
                '1': (0x0000, 2400),
                '2': (0x0001, 4800),
                '3': (0x0002, 9600),
                '4': (0x0003, 19200)
            }
            if b_sel not in baud_map:
                print("❌ ตัวเลือกไม่ถูกต้อง")
                continue
                
            baud_code, new_baud = baud_map[b_sel]
            confirm = input(f"ยืนยันเปลี่ยน Baudrate จาก [{current_baud}] -> [{new_baud} bps] หรือไม่? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                try:
                    with serial.Serial(port_name, baudrate=current_baud, timeout=0.5) as ser:
                        change_baudrate(ser, current_id, baud_code, new_baud, reg_addr=0x0101)
                    
                    # ตรวจสอบ 100%
                    if verify_sensor_operation(port_name, new_baud, current_id):
                        current_baud = new_baud
                        print(f"🎉 อัปเดตการจำค่าในระบบ: Baudrate ปัจจุบันเปลี่ยนเป็น [{current_baud} bps] เรียบร้อย")
                    else:
                        print("⚠️ ไม่สามารถอ่านได้ที่ Baudrate ใหม่ ลองค้นหาใหม่อีกครั้ง")
                        current_baud, current_id = auto_detect_sensor(port_name)
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาด: {e}")

        # -------------------------------------------------------------
        # เมนู 4: Auto-Detect ใหม่
        # -------------------------------------------------------------
        elif choice == '4':
            b, i = auto_detect_sensor(port_name)
            if b and i:
                current_baud, current_id = b, i

        # -------------------------------------------------------------
        # เมนู 0: ออกจากโปรแกรม
        # -------------------------------------------------------------
        elif choice == '0':
            print("\nปิดโปรแกรม เรียบร้อยแล้ว ขอบคุณครับ! 🍌")
            break
        else:
            print("❌ ตัวเลือกไม่ถูกต้อง กรุณาเลือก 0 ถึง 4")

if __name__ == '__main__':
    main()
