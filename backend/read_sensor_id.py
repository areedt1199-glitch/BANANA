import serial
import struct
import time

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

def query(ser, slave_id, func, reg_start, count):
    payload = struct.pack('>BBHH', slave_id, func, reg_start, count)
    frame = payload + calc_crc(payload)
    ser.reset_input_buffer()
    ser.write(frame)
    time.sleep(0.12)
    resp = ser.read(64)
    return resp

def run():
    print("Connecting to COM4 at 4800 baud...")
    with serial.Serial('COM4', baudrate=4800, timeout=1) as ser:
        # 1. Read Standard Registers 0x0000 - 0x0006
        resp = query(ser, 1, 3, 0x0000, 7)
        print("\n--- Live Modbus Telemetry (Reg 0x0000 - 0x0006) ---")
        if resp and len(resp) >= 19:
            data = resp[3:17]
            vals = struct.unpack('>7H', data)
            print(f"Raw Hex: {resp.hex(' ')}")
            print(f"Moisture:    {vals[0] / 10.0:.1f} %")
            print(f"Temperature: {vals[1] / 10.0:.1f} C")
            print(f"EC:          {vals[2]} us/cm ({vals[2] / 1000.0:.3f} dS/m)")
            print(f"pH:          {vals[3] / 10.0:.1f}")
            print(f"Nitrogen:    {vals[4]} mg/kg")
            print(f"Phosphorus:  {vals[5]} mg/kg")
            print(f"Potassium:   {vals[6]} mg/kg")
        else:
            print("No response for 0x0000 - 0x0006")

        # 2. Try Function 0x11 (Report Slave ID)
        ser.reset_input_buffer()
        f11 = bytes([0x01, 0x11]) + calc_crc(bytes([0x01, 0x11]))
        ser.write(f11)
        time.sleep(0.15)
        resp11 = ser.read(64)
        if resp11:
            print(f"\n--- Function 0x11 (Report Slave ID) ---")
            print(f"Response: {resp11.hex(' ')}")
            print(f"ASCII: {resp11}")

        # 3. Check Address Register 0x0100 (Address / Baud / Model in many RS485 sensors)
        for reg in [0x0020, 0x0100, 0x0200, 0x07D0]:
            r = query(ser, 1, 3, reg, 4)
            if r and len(r) >= 5 and r[1] == 3:
                print(f"\n--- Register 0x{reg:04X} ---")
                print(f"Hex: {r.hex(' ')}")
                regs = struct.unpack(f'>{r[2]//2}H', r[3:3+r[2]])
                print(f"Values: {regs}")

if __name__ == '__main__':
    run()
