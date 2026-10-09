import unittest
from unittest.mock import patch, MagicMock
from loyalty import app, compute_status


def mock_conn(fetchone=None, fetchall=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


class LoyaltyTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_compute_status(self):
        self.assertEqual(compute_status(0), ("BRONZE", 5))
        self.assertEqual(compute_status(9), ("BRONZE", 5))
        self.assertEqual(compute_status(10), ("SILVER", 7))
        self.assertEqual(compute_status(19), ("SILVER", 7))
        self.assertEqual(compute_status(20), ("GOLD", 10))
        self.assertEqual(compute_status(100), ("GOLD", 10))

    def test_get_loyalty_no_header(self):
        r = self.client.get("/api/v1/loyalty")
        self.assertEqual(r.status_code, 400)

    @patch("loyalty.get_conn")
    def test_get_loyalty_not_found(self, mock_get):
        conn, _ = mock_conn(fetchone=None)
        mock_get.return_value = conn
        r = self.client.get("/api/v1/loyalty", headers={"X-User-Name": "X"})
        self.assertEqual(r.status_code, 404)

    @patch("loyalty.get_conn")
    def test_get_loyalty_ok(self, mock_get):
        conn, _ = mock_conn(fetchone=("Test Max", 25, "GOLD", 10))
        mock_get.return_value = conn
        r = self.client.get("/api/v1/loyalty", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "GOLD")
        self.assertEqual(body["discount"], 10)
        self.assertEqual(body["reservationCount"], 25)

    @patch("loyalty.get_conn")
    def test_increment_ok(self, mock_get):
        conn, cur = mock_conn(fetchone=(25,))
        mock_get.return_value = conn
        r = self.client.post("/api/v1/loyalty/increment", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["reservationCount"], 26)
        self.assertEqual(r.get_json()["status"], "GOLD")

    @patch("loyalty.get_conn")
    def test_decrement_downgrades(self, mock_get):
        conn, cur = mock_conn(fetchone=(20,))
        mock_get.return_value = conn
        r = self.client.post("/api/v1/loyalty/decrement", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["reservationCount"], 19)
        self.assertEqual(r.get_json()["status"], "SILVER")
        self.assertEqual(r.get_json()["discount"], 7)

    @patch("loyalty.get_conn")
    def test_decrement_not_below_zero(self, mock_get):
        conn, _ = mock_conn(fetchone=(0,))
        mock_get.return_value = conn
        r = self.client.post("/api/v1/loyalty/decrement", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.get_json()["reservationCount"], 0)


if __name__ == "__main__":
    unittest.main()
