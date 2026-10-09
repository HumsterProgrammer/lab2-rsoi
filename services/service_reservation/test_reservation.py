import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from reservation import app


HOTEL_ROW = (
    1, "049161bb-badd-4fa8-9d90-87c9a82b0668",
    "Ararat Park Hyatt Moscow", "Россия", "Москва",
    "Неглинная ул., 4", 5, 10000,
)

RES_ROW = (
    "9b4ba1f7-e5ac-465b-ace4-7b54dec20f9a",
    "PAID",
    datetime(2021, 10, 8, tzinfo=timezone.utc),
    datetime(2021, 10, 11, tzinfo=timezone.utc),
    "11111111-1111-1111-1111-111111111111",
    "049161bb-badd-4fa8-9d90-87c9a82b0668",
    "Ararat Park Hyatt Moscow", "Россия", "Москва",
    "Неглинная ул., 4", 5, 10000,
    "Test Max",
)


def mock_conn(fetchone=None, fetchall=None, count=0):
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [count, fetchone] if count else None
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class ReservationTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("reservation.get_conn")
    def test_list_hotels(self, mock_get):
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = (1,)
        cur.fetchall.return_value = [HOTEL_ROW[1:]]
        conn.cursor.return_value = cur
        mock_get.return_value = conn

        r = self.client.get("/api/v1/hotels?page=0&size=10")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["page"], 0)
        self.assertEqual(body["totalElements"], 1)
        self.assertEqual(body["items"][0]["hotelUid"], "049161bb-badd-4fa8-9d90-87c9a82b0668")
        self.assertEqual(body["items"][0]["price"], 10000)

    @patch("reservation.get_conn")
    def test_create_reservation_no_header(self, mock_get):
        r = self.client.post("/api/v1/reservations", json={
            "hotelUid": "049161bb-badd-4fa8-9d90-87c9a82b0668",
            "startDate": "2021-10-08", "endDate": "2021-10-11",
        })
        self.assertEqual(r.status_code, 400)

    @patch("reservation.get_conn")
    def test_create_reservation_invalid_dates(self, mock_get):
        r = self.client.post(
            "/api/v1/reservations",
            headers={"X-User-Name": "Test Max"},
            json={"hotelUid": "x", "startDate": "2021-10-11", "endDate": "2021-10-08"},
        )
        self.assertEqual(r.status_code, 400)

    @patch("reservation.requests.post")
    @patch("reservation.requests.get")
    @patch("reservation.get_conn")
    def test_create_reservation_ok(self, mock_get_conn, mock_get, mock_post):
        # db
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = HOTEL_ROW
        conn.cursor.return_value = cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = conn

        # gateway get -> loyalty
        loyalty_resp = MagicMock(status_code=200)
        loyalty_resp.json.return_value = {"status": "GOLD", "discount": 10, "reservationCount": 25}
        mock_get.return_value = loyalty_resp

        # gateway post -> payments
        pay_resp = MagicMock(status_code=200)
        pay_resp.json.return_value = {"paymentUid": "11111111-1111-1111-1111-111111111111",
                                      "status": "PAID", "price": 27000}
        mock_post.return_value = pay_resp

        r = self.client.post(
            "/api/v1/reservations",
            headers={"X-User-Name": "Test Max"},
            json={"hotelUid": HOTEL_ROW[1], "startDate": "2021-10-08", "endDate": "2021-10-11"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["discount"], 10)
        self.assertEqual(body["payment"]["price"], 27000)
        self.assertEqual(body["status"], "PAID")

    @patch("reservation.get_conn")
    def test_get_reservations_no_header(self, mock_get):
        r = self.client.get("/api/v1/reservations")
        self.assertEqual(r.status_code, 400)

    @patch("reservation.requests.get")
    @patch("reservation.get_conn")
    def test_get_reservation_not_found(self, mock_get_conn, mock_get):
        conn, _ = mock_conn(fetchone=None)
        mock_get_conn.return_value = conn
        r = self.client.get("/api/v1/reservations/uid", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 404)

    @patch("reservation.requests.post")
    @patch("reservation.get_conn")
    def test_delete_already_canceled(self, mock_get_conn, mock_post):
        row = ("pay-1", "CANCELED", "Test Max")
        conn, _ = mock_conn(fetchone=row)
        mock_get_conn.return_value = conn
        r = self.client.delete("/api/v1/reservations/uid", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 409)

    @patch("reservation.requests.post")
    @patch("reservation.get_conn")
    def test_delete_ok(self, mock_get_conn, mock_post):
        row = ("pay-1", "PAID", "Test Max")
        conn, _ = mock_conn(fetchone=row)
        mock_get_conn.return_value = conn
        mock_post.return_value = MagicMock(status_code=200)
        r = self.client.delete("/api/v1/reservations/uid", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 204)


if __name__ == "__main__":
    unittest.main()
