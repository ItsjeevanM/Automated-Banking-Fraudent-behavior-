from fastapi import FastAPI
from database import create_database

from database import (
    create_database,
    add_transaction,
    get_transactions
)

app = FastAPI()

create_database()


@app.get("/")
def home():
    return {"message": "Backend is running!"}


@app.get("/hello")
def hello():
    return {"message": "Hello Tejasvi!"}

@app.get("/add-test")
def add_test():

    add_transaction(
        "Debit",
        500,
        12000,
        "2026-06-02",
        "10:00",
        "UPI",
        "Amazon"
    )

    return {"message": "Transaction added"}

@app.get("/transactions")
def transactions():

    data = get_transactions()

    return {"transactions": data}