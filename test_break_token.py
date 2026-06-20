import sys
sys.path.append('src')
from db import DatabaseManager

db = DatabaseManager()
accounts = db.get_accounts()

if not accounts:
    # insert a dummy account
    db.add_account("SimulatedBad", "apikey", "123", "bad_token")
    print("Added simulated bad account.")
else:
    # break the first account
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE accounts SET auth_token = 'invalid_token' WHERE id = %s", (accounts[0]['id'],))
            conn.commit()
    print("Broke the first account's token.")
