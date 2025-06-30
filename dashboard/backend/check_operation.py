import sqlite3
import json

conn = sqlite3.connect('dashboard.db')
cursor = conn.cursor()

# Get the most recent operations
cursor.execute('SELECT operation_id, started_at, last_updated, insights FROM operations ORDER BY rowid DESC LIMIT 5')
results = cursor.fetchall()

if results:
    print("=== Most Recent Operations ===")
    for operation_id, started_at, last_updated, insights in results:
        print(f'Operation ID: {operation_id}')
        print(f'Started: {started_at}')
        print(f'Last Updated: {last_updated}')
        if insights:
            try:
                parsed = json.loads(insights)
                print(f'✅ Has insights: {list(parsed.keys())}')
            except:
                print(f'⚠️ Raw insights: {insights[:100]}...')
        else:
            print('❌ No insights')
        print('---')
else:
    print('No operations found')

conn.close() 