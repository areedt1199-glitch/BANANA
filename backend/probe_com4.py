import serial
import time
import struct

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

def build_modbus_frame(slave_id, func, reg_start, count):
    payload = struct.pack('>BBHH', slave_id, func, reg_start, count)
    return payload + calc_crc(payload)

def probe_port(port='COM4'):
    baud_rates = [9600, 4800, 19200, 115200]
    
    print(f"=== Probing {port} ===")
    
    for baud in baud_rates:
        print(f"\n--- Testing Baud Rate: {baud} ---")
        try:
            with serial.Serial(port, baudrate=baud, timeout=0.8, write_timeout=0.8) as ser:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Check passive read first (if sensor is continuously streaming)
                time.sleep(0.3)
                if ser.in_waiting > 0:
                    raw = ser.read(ser.in_waiting)
                    print(f"[*] Passive incoming data received: {raw.hex(' ')} (ASCII: {repr(raw)})")
                
                # Query Standard 7-in-1 frame (Slave 1, Func 3, Reg 0, Count 7)
                frame1 = build_modbus_frame(1, 3, 0, 7)
                ser.write(frame1)
                time.sleep(0.15)
                resp = ser.read(64)
                if resp:
                    print(f"[!] SUCCESS! Modbus 7-in-1 Response (Slave 1, Reg 0-6): {resp.hex(' ')}")
                    parse_7in1(resp)
                    return
                
                # Query Slave 1, Func 3, Reg 0, Count 2
                frame2 = build_modbus_frame(1, 3, 0, 2)
                ser.write(frame2)
                time.sleep(0.15)
                resp = ser.read(64)
                if resp:
                    print(f"[!] SUCCESS! Modbus Response (Slave 1, Reg 0-1): {resp.hex(' ')}")
                    return
                
                # Broadcast query (Slave 255/0xFF or Address Query for common Chinese sensors)
                # Query slave address command: 0xFF 0x03 0x07 0xD0 0x00 0x01
                addr_query = bytes([0xFF, 0x03, 0x07, 0xD0, 0x00, 0x01]) + calc_crc(bytes([0xFF, 0x03, 0x07, 0xD0, 0x00, 0x01]))
                ser.write(addr_query)
                time.sleep(0.15)
                resp = ser.read(64)
                if resp:
                    print(f"[!] SUCCESS! Address/ID Query Response: {resp.hex(' ')}")
                    return
                    
                # Scan common slave IDs 1..5
                for s_id in range(1, 6):
                    f = build_modbus_frame(s_id, 3, 0, 1)
                    ser.write(f)
                    time.sleep(0.08)
                    r = ser.read(32)
                    if r:
                        print(f"[!] Detected Slave ID {s_id}: {r.hex(' ')}")
                        return
                        
        except Exception as e:
            print(f"Error on {port} at {baud}: {e}")

def parse_7in1(resp: bytes):
    if len(resp) >= 19 and resp[1] == 3:
        data = resp[3:]
        moisture = struct.unpack('>H', data[0:2])[0] / 10.0
        temp = struct.unpack('>H', data[2:4])[0] / 10.0
        ec = struct.unpack('>H', data[4:6])[0]
        ph = struct.unpack('>H', data[6:8])[0] / 10.0
        n = struct.unpack('>H', data[8:10])[0]
        p = struct.unpack('>H', data[10:12])[0]
        k = struct.unpack('>H', data[12:14])[0]
        print(f"    - Moisture: {moisture:.1f}%")
        print(f"    - Temp: {temp:.1f} °C")
        print(f"    - EC: {ec} us/cm ({ec/1000.0:.3f} dS/m)")
        print(f"    - pH: {ph:.1f}")
        print(f"    - N: {n} mg/kg")
        print(f"    - P: {p} mg/kg")
        print(f"    - K: {k} mg/kg")

if __name__ == '__main__':
    probe_port('COM4')
