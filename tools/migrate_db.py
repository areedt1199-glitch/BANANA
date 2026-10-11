import sqlite3

conn = sqlite3.connect('backend/banana_smart_farm.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(devices)')
existing = [c[1] for c in cursor.fetchall()]

new_cols = [
    ('sensor_model', "VARCHAR(50) DEFAULT 'SN-3002GZWS-NO1-65535'"),
    ('baud_rate', 'INTEGER DEFAULT 9600'),
    ('modbus_slave_id', 'INTEGER DEFAULT 1'),
    ('temp_offset', 'FLOAT DEFAULT 0.0'),
    ('rh_offset', 'FLOAT DEFAULT 0.0'),
    ('lux_offset', 'FLOAT DEFAULT 0.0'),
    ('ec_offset', 'FLOAT DEFAULT 0.0'),
    ('ph_offset', 'FLOAT DEFAULT 0.0'),
]

for name, col_def in new_cols:
    if name not in existing:
        cursor.execute(f"ALTER TABLE devices ADD COLUMN {name} {col_def}")
        print(f"Added column: {name}")
    else:
        print(f"Column already exists: {name}")

conn.commit()
conn.close()
print("Devices schema updated successfully!")
