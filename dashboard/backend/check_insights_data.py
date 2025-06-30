import sqlite3
import json

conn = sqlite3.connect('dashboard.db')
cursor = conn.cursor()

cursor.execute('SELECT operation_id, insights FROM operations WHERE operation_id LIKE "6e762e62%"')
result = cursor.fetchone()

if result:
    operation_id, insights_json = result
    print(f'Operation ID: {operation_id}')
    print('Raw insights JSON:')
    if insights_json:
        insights = json.loads(insights_json)
        print(json.dumps(insights, indent=2))
    else:
        print('No insights data')
else:
    print('Operation not found')

conn.close() 