import sqlite3, os
path = "transactions.db"
print("File exists:", os.path.exists(path))
c = sqlite3.connect(path)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
c.close()
