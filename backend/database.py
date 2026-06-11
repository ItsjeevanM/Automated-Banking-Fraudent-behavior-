import sqlite3

DATABASE_NAME = "transactions.db"


def create_database():
    conn = sqlite3.connect(DATABASE_NAME)

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debit_credit TEXT,
        amount REAL,
        balance REAL,
        date TEXT,
        time TEXT,
        transaction_type TEXT,
        merchant TEXT
    )
    """)
def add_transaction(
    debit_credit,
    amount,
    balance,
    date,
    time,
    transaction_type,
    merchant
):
    conn = sqlite3.connect(DATABASE_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO transactions
        (
            debit_credit,
            amount,
            balance,
            date,
            time,
            transaction_type,
            merchant
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (
        debit_credit,
        amount,
        balance,
        date,
        time,
        transaction_type,
        merchant
    ))

    conn.commit()
    conn.close()

def get_transactions():
    conn = sqlite3.connect(DATABASE_NAME)

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM transactions")

    rows = cursor.fetchall()

    conn.close()

    return rows