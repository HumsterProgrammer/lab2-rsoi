import unittest
from unittest.mock import patch, MagicMock
from payment import app


def mock_conn(fetchone=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class PaymentTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("payment.get_conn")
    def test_create_payment(self, mock_get):
        conn, _ = mock_conn()
        mock_get.return_value = conn
        r = self.client.post("/api/v1/payments", json={"price": 27000})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "PAID")
        self.assertEqual(body["price"], 27000)
        self.assertIn("paymentUid", body)

    @patch("payment.get_conn")
    def test_create_payment_missing_price(self, mock_get):
        conn, _ = mock_conn()
        mock_get.return_value = conn
        r = self.client.post("/api/v1/payments", json={})
        self.assertEqual(r.status_code, 400)

    @patch("payment.get_conn")
    def test_get_payment_ok(self, mock_get):
        conn, _ = mock_conn(fetchone=("11111111-1111-1111-1111-111111111111", "PAID", 5000))
        mock_get.return_value = conn
        r = self.client.get("/api/v1/payments/11111111-1111-1111-1111-111111111111")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["price"], 5000)

    @patch("payment.get_conn")
    def test_get_payment_not_found(self, mock_get):
        conn, _ = mock_conn(fetchone=None)
        mock_get.return_value = conn
        r = self.client.get("/api/v1/payments/unknown")
        self.assertEqual(r.status_code, 404)

    @patch("payment.get_conn")
    def test_cancel_ok(self, mock_get):
        conn, _ = mock_conn(fetchone=("PAID",))
        mock_get.return_value = conn
        r = self.client.post("/api/v1/payments/uid-1/cancel")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "CANCELED")

    @patch("payment.get_conn")
    def test_cancel_already(self, mock_get):
        conn, _ = mock_conn(fetchone=("CANCELED",))
        mock_get.return_value = conn
        r = self.client.post("/api/v1/payments/uid-1/cancel")
        self.assertEqual(r.status_code, 409)

    @patch("payment.get_conn")
    def test_cancel_not_found(self, mock_get):
        conn, _ = mock_conn(fetchone=None)
        mock_get.return_value = conn
        r = self.client.post("/api/v1/payments/uid-1/cancel")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
