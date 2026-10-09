import os
import time
import uuid
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "payments"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    for _ in range(30):
        try:
            conn = get_conn()
            break
        except psycopg2.OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("Cannot connect to DB")
    with conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payment (
                id SERIAL PRIMARY KEY,
                payment_uid uuid NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL
                    CHECK (status IN ('PAID','CANCELED')),
                price INT NOT NULL
            );
        """)
    conn.close()


@app.route("/manage/health", methods=["GET"])
def health():
    return "Up", 200

@app.route("/api/v1/payments", methods=["POST"])
def create_payment():
    data = request.get_json(silent=True) or {}
    price = data.get("price")
    if price is None or not isinstance(price, (int, float)):
        return jsonify({"message": "price is required"}), 400
    payment_uid = str(uuid.uuid4())
    price = int(price)
    conn = get_conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO payment (payment_uid, status, price) VALUES (%s, 'PAID', %s)",
            (payment_uid, price),
        )
    conn.close()
    return jsonify({"paymentUid": payment_uid, "status": "PAID", "price": price}), 200


@app.route("/api/v1/payments/<payment_uid>", methods=["GET"])
def get_payment(payment_uid):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT payment_uid, status, price FROM payment WHERE payment_uid=%s",
            (payment_uid,),
        )
        row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"message": "Payment not found"}), 404
    return jsonify({"paymentUid": str(row[0]), "status": row[1], "price": row[2]}), 200


@app.route("/api/v1/payments/<payment_uid>/cancel", methods=["POST"])
def cancel_payment(payment_uid):
    conn = get_conn()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM payment WHERE payment_uid=%s FOR UPDATE", (payment_uid,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"message": "Payment not found"}), 404
        if row[0] == "CANCELED":
            conn.close()
            return jsonify({"message": "Payment already canceled"}), 409
        cur.execute("UPDATE payment SET status='CANCELED' WHERE payment_uid=%s", (payment_uid,))
    conn.close()
    return jsonify({"paymentUid": payment_uid, "status": "CANCELED"}), 200


if __name__ == "__main__":
    #init_db()
    app.run(host="0.0.0.0", port=8060)
