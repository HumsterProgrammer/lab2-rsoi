import os
import time
import uuid
import math
import requests
from datetime import date
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "reservations"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
}
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")


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
            CREATE TABLE IF NOT EXISTS hotels (
                id SERIAL PRIMARY KEY,
                hotel_uid uuid NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                country VARCHAR(80) NOT NULL,
                city VARCHAR(80) NOT NULL,
                address VARCHAR(255) NOT NULL,
                stars INT,
                price INT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservation (
                id SERIAL PRIMARY KEY,
                reservation_uid uuid UNIQUE NOT NULL,
                username VARCHAR(80) NOT NULL,
                payment_uid uuid NOT NULL,
                hotel_id INT REFERENCES hotels (id),
                status VARCHAR(20) NOT NULL
                    CHECK (status IN ('PAID','CANCELED')),
                start_date TIMESTAMP WITH TIME ZONE,
                end_date TIMESTAMP WITH TIME ZONE
            );
        """)
        cur.execute("SELECT COUNT(*) FROM hotels")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO hotels (hotel_uid, name, country, city, address, stars, price) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("049161bb-badd-4fa8-9d90-87c9a82b0668",
                 "Ararat Park Hyatt Moscow", "Россия", "Москва",
                 "Неглинная ул., 4", 5, 10000),
            )
    conn.close()


def _hotel_public(row):
    return {
        "hotelUid": str(row[0]),
        "name": row[1],
        "country": row[2],
        "city": row[3],
        "address": row[4],
        "stars": row[5],
        "price": row[6],
    }


def _hotel_info(row):
    return {
        "hotelUid": str(row[0]),
        "name": row[1],
        "fullAddress": f"{row[2]}, {row[3]}, {row[4]}",
        "stars": row[5],
    }


# -------- HOTELS --------

@app.route("/manage/health", methods=["GET"])
def health():
    return "Up", 200

@app.route("/api/v1/hotels", methods=["GET"])
def list_hotels():
    try:
        page = int(request.args.get("page", 0))
        size = int(request.args.get("size", 10))
    except ValueError:
        return jsonify({"message": "Invalid pagination params"}), 400
    if page < 0 or size < 1:
        return jsonify({"message": "Invalid pagination params"}), 400
    offset = page * size
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM hotels")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT hotel_uid, name, country, city, address, stars, price "
            "FROM hotels ORDER BY id LIMIT %s OFFSET %s",
            (size, offset),
        )
        rows = cur.fetchall()
        print(rows)
    conn.close()
    return jsonify({
        "page": page,
        "pageSize": len(rows),
        "totalElements": total,
        "items": [_hotel_public(r) for r in rows],
    }), 200


@app.route("/api/v1/hotels/<hotel_uid>", methods=["GET"])
def get_hotel(hotel_uid):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT hotel_uid, name, country, city, address, stars, price "
            "FROM hotels WHERE hotel_uid=%s",
            (hotel_uid,),
        )
        row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"message": "Hotel not found"}), 404
    return jsonify(_hotel_public(row)), 200


# -------- HELPERS --------

def _payment_info(payment_uid):
    try:
        r = requests.get(f"{GATEWAY_URL}/api/v1/internal/payments/{payment_uid}", timeout=10)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.json()


def _build_reservation_response(row):
    """row: (reservation_uid, status, start_date, end_date, payment_uid,
             hotel_uid, name, country, city, address, stars, price)"""
    payment = _payment_info(str(row[4])) or {"status": "PAID", "price": 0}
    return {
        "reservationUid": str(row[0]),
        "hotel": {
            "hotelUid": str(row[5]),
            "name": row[6],
            "fullAddress": f"{row[7]}, {row[8]}, {row[9]}",
            "stars": row[10],
        },
        "startDate": row[2].date().isoformat() if row[2] else None,
        "endDate": row[3].date().isoformat() if row[3] else None,
        "status": row[1],
        "payment": {
            "status": payment.get("status", "PAID"),
            "price": payment.get("price", 0),
        },
    }


# -------- RESERVATIONS --------

@app.route("/api/v1/reservations", methods=["GET"])
def list_reservations():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.reservation_uid, r.status, r.start_date, r.end_date, r.payment_uid,
                   h.hotel_uid, h.name, h.country, h.city, h.address, h.stars, h.price
            FROM reservation r
            JOIN hotels h ON h.id = r.hotel_id
            WHERE r.username = %s
            ORDER BY r.id
        """, (username,))
        rows = cur.fetchall()
    conn.close()
    return jsonify([_build_reservation_response(r) for r in rows]), 200


@app.route("/api/v1/reservations/<reservation_uid>", methods=["GET"])
def get_reservation(reservation_uid):
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.reservation_uid, r.status, r.start_date, r.end_date, r.payment_uid,
                   h.hotel_uid, h.name, h.country, h.city, h.address, h.stars, h.price,
                   r.username
            FROM reservation r
            JOIN hotels h ON h.id = r.hotel_id
            WHERE r.reservation_uid = %s
        """, (reservation_uid,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"message": "Reservation not found"}), 404
    if row[12] != username:
        return jsonify({"message": "Reservation does not belong to user"}), 404
    return jsonify(_build_reservation_response(row[:12])), 200


@app.route("/api/v1/reservations", methods=["POST"])
def create_reservation():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400
    data = request.get_json(silent=True) or {}
    hotel_uid = data.get("hotelUid")
    start_date_str = data.get("startDate")
    end_date_str = data.get("endDate")
    if not hotel_uid or not start_date_str or not end_date_str:
        return jsonify({"message": "hotelUid, startDate, endDate are required"}), 400
    try:
        sd = date.fromisoformat(start_date_str)
        ed = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"message": "Invalid date format"}), 400
    if sd >= ed:
        return jsonify({"message": "startDate must be before endDate"}), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, hotel_uid, name, country, city, address, stars, price "
            "FROM hotels WHERE hotel_uid=%s",
            (hotel_uid,),
        )
        hotel = cur.fetchone()
    if not hotel:
        conn.close()
        return jsonify({"message": "Hotel not found"}), 400

    nights = (ed - sd).days
    total = hotel[7] * nights

    # 1) discount via gateway -> loyalty
    try:
        r = requests.get(
            f"{GATEWAY_URL}/api/v1/internal/loyalty",
            headers={"X-User-Name": username}, timeout=10,
        )
    except requests.RequestException:
        conn.close()
        return jsonify({"message": "Loyalty service unavailable"}), 502
    if r.status_code != 200:
        conn.close()
        return jsonify(r.json()), r.status_code
    discount = r.json()["discount"]
    final_price = math.ceil(total * (100 - discount) / 100)

    # 2) create payment via gateway -> payment
    try:
        r = requests.post(
            f"{GATEWAY_URL}/api/v1/internal/payments",
            json={"price": final_price}, timeout=10,
        )
    except requests.RequestException:
        conn.close()
        return jsonify({"message": "Payment service unavailable"}), 502
    if r.status_code != 200:
        conn.close()
        return jsonify(r.json()), r.status_code
    payment = r.json()
    payment_uid = payment["paymentUid"]

    reservation_uid = str(uuid.uuid4())
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reservation "
            "(reservation_uid, username, payment_uid, hotel_id, status, start_date, end_date) "
            "VALUES (%s, %s, %s, %s, 'PAID', %s, %s)",
            (reservation_uid, username, payment_uid, hotel[0], sd, ed),
        )
    conn.close()

    # 3) increment loyalty via gateway
    try:
        requests.post(
            f"{GATEWAY_URL}/api/v1/internal/loyalty/increment",
            headers={"X-User-Name": username}, timeout=10,
        )
    except requests.RequestException:
        pass  # не падаем, бронь уже создана

    return jsonify({
        "reservationUid": reservation_uid,
        "hotelUid": hotel_uid,
        "startDate": start_date_str,
        "endDate": end_date_str,
        "discount": discount,
        "status": "PAID",
        "payment": {"status": "PAID", "price": final_price},
    }), 200


@app.route("/api/v1/reservations/<reservation_uid>", methods=["DELETE"])
def delete_reservation(reservation_uid):
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400
    conn = get_conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT payment_uid, status, username FROM reservation WHERE reservation_uid=%s FOR UPDATE",
            (reservation_uid,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"message": "Reservation not found"}), 404
        if row[2] != username:
            conn.close()
            return jsonify({"message": "Reservation does not belong to user"}), 404
        payment_uid, status, _ = row
        if status == "CANCELED":
            conn.close()
            return jsonify({"message": "Reservation already canceled"}), 409
        cur.execute(
            "UPDATE reservation SET status='CANCELED' WHERE reservation_uid=%s",
            (reservation_uid,),
        )
    conn.close()

    # cancel payment via gateway
    try:
        requests.post(f"{GATEWAY_URL}/api/v1/internal/payments/{payment_uid}/cancel", timeout=10)
    except requests.RequestException:
        pass

    # decrement loyalty via gateway
    try:
        requests.post(
            f"{GATEWAY_URL}/api/v1/internal/loyalty/decrement",
            headers={"X-User-Name": username}, timeout=10,
        )
    except requests.RequestException:
        pass

    return "", 204


if __name__ == "__main__":
    #init_db()
    app.run(host="0.0.0.0", port=8070)
