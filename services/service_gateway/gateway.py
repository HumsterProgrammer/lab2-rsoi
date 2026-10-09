import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

RESERVATION_URL = os.environ.get("RESERVATION_URL", "http://localhost:8070")
PAYMENT_URL = os.environ.get("PAYMENT_URL", "http://localhost:8060")
LOYALTY_URL = os.environ.get("LOYALTY_URL", "http://localhost:8050")


def _forward(method, url, pass_headers=None, params=None, json_body=None):
    headers = {}
    if pass_headers:
        for h in pass_headers:
            v = request.headers.get(h)
            if v:
                headers[h] = v
    try:
        resp = requests.request(method, url, headers=headers, params=params,
                                json=json_body, timeout=30)
    except requests.RequestException as e:
        return jsonify({"message": f"Upstream error: {e}"}), 502
    if resp.status_code == 204 or not resp.content:
        return "", resp.status_code
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return resp.text, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "text/plain")}


# ============ EXTERNAL ============

@app.route("/api/v1/hotels", methods=["GET"])
def get_hotels():
    return _forward("GET", f"{RESERVATION_URL}/api/v1/hotels",
                    params=request.args.to_dict())


@app.route("/api/v1/me", methods=["GET"])
def get_me():
    username = request.headers.get("X-User-Name")
    if not username:
        return jsonify({"message": "X-User-Name header is required"}), 400
    try:
        r_res = requests.get(
            f"{RESERVATION_URL}/api/v1/reservations",
            headers={"X-User-Name": username}, timeout=30,
        )
        r_loy = requests.get(
            f"{LOYALTY_URL}/api/v1/loyalty",
            headers={"X-User-Name": username}, timeout=30,
        )
    except requests.RequestException as e:
        return jsonify({"message": f"Upstream error: {e}"}), 502
    if r_loy.status_code != 200:
        return jsonify(r_loy.json()), r_loy.status_code
    reservations = r_res.json() if r_res.status_code == 200 else []
    return jsonify({
        "reservations": reservations,
        "loyalty": r_loy.json(),
    }), 200


@app.route("/api/v1/reservations", methods=["GET"])
def list_reservations():
    return _forward("GET", f"{RESERVATION_URL}/api/v1/reservations",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/reservations", methods=["POST"])
def create_reservation():
    return _forward("POST", f"{RESERVATION_URL}/api/v1/reservations",
                    pass_headers=["X-User-Name"],
                    json_body=request.get_json(silent=True) or {})


@app.route("/api/v1/reservations/<uuid:reservation_uid>", methods=["GET"])
def get_reservation(reservation_uid):
    return _forward("GET", f"{RESERVATION_URL}/api/v1/reservations/{reservation_uid}",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/reservations/<uuid:reservation_uid>", methods=["DELETE"])
def delete_reservation(reservation_uid):
    return _forward("DELETE", f"{RESERVATION_URL}/api/v1/reservations/{reservation_uid}",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/loyalty", methods=["GET"])
def get_loyalty():
    return _forward("GET", f"{LOYALTY_URL}/api/v1/loyalty",
                    pass_headers=["X-User-Name"])


# ============ INTERNAL ============

@app.route("/api/v1/internal/hotels/<hotel_uid>", methods=["GET"])
def internal_get_hotel(hotel_uid):
    return _forward("GET", f"{RESERVATION_URL}/api/v1/hotels/{hotel_uid}")


@app.route("/api/v1/internal/loyalty", methods=["GET"])
def internal_get_loyalty():
    return _forward("GET", f"{LOYALTY_URL}/api/v1/loyalty",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/internal/loyalty/increment", methods=["POST"])
def internal_loyalty_increment():
    return _forward("POST", f"{LOYALTY_URL}/api/v1/loyalty/increment",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/internal/loyalty/decrement", methods=["POST"])
def internal_loyalty_decrement():
    return _forward("POST", f"{LOYALTY_URL}/api/v1/loyalty/decrement",
                    pass_headers=["X-User-Name"])


@app.route("/api/v1/internal/payments", methods=["POST"])
def internal_create_payment():
    return _forward("POST", f"{PAYMENT_URL}/api/v1/payments",
                    json_body=request.get_json(silent=True) or {})


@app.route("/api/v1/internal/payments/<payment_uid>", methods=["GET"])
def internal_get_payment(payment_uid):
    return _forward("GET", f"{PAYMENT_URL}/api/v1/payments/{payment_uid}")


@app.route("/api/v1/internal/payments/<payment_uid>/cancel", methods=["POST"])
def internal_cancel_payment(payment_uid):
    return _forward("POST", f"{PAYMENT_URL}/api/v1/payments/{payment_uid}/cancel")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
