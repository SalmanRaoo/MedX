import sqlite3
import os

# Looking for the file visible in your screenshot: 'hospital.db'
db_path = "hospital.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # SQL query to get table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"\n📊 FOUND {len(tables)} TABLES IN 'hospital.db':\n" + "="*40)
    for i, table in enumerate(tables):
        print(f"{i+1}. {table[0]}")
    print("="*40)
    conn.close()
else:
    print(f"❌ Could not find {db_path} in this folder.")