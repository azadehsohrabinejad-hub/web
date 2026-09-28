import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os

app_root = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(app_root, "shifts.db")
backup_dir = os.path.join(app_root, "backups")
os.makedirs(backup_dir, exist_ok=True)

# محاسبه تاریخ شروع و پایان هفته جاری (شنبه تا جمعه)
today = datetime.now().date()
start_of_week = today - timedelta(days=today.weekday() + 1)  # شنبه
end_of_week = start_of_week + timedelta(days=6)              # جمعه

conn = sqlite3.connect(db_path)
query = """
SELECT date, name, shift_type, entry_time, exit_time, duration
FROM shifts
WHERE date BETWEEN ? AND ?
ORDER BY date, entry_time
"""
df = pd.read_sql_query(query, conn, params=(start_of_week, end_of_week))
conn.close()

if not df.empty:
    filename = f"shift_weekly_{start_of_week}_to_{end_of_week}.xlsx"
    filepath = os.path.join(backup_dir, filename)
    df.to_excel(filepath, index=False, engine='openpyxl')
    print(f"بکاپ هفتگی اکسل ذخیره شد: {filename}")
else:
    print("هیچ شیفتی در این هفته ثبت نشده")
