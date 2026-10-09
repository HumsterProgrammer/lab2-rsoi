import unittest
from unittest.mock import patch, MagicMock
from gateway import app


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("gateway.requests.request")
    def test_get_hotels_proxies(self, mock_req):
        resp = MagicMock(status_code=200, content=b"{}")
        resp.json.return_value = {"page": 0, "pageSize": 1, "totalElements": 1, "items": []}
        mock_req.return_value = resp
        r = self.client.get("/api/v1/hotels?page=0&size=10")
        self.assertEqual(r.status_code, 200)
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], "GET")
        self.assertTrue(args[1].endswith("/api/v1/hotels"))

    @patch("gateway.requests.get")
    def test_get_me_ok(self, mock_get):
        res_resp = MagicMock(status_code=200)
        res_resp.json.return_value = [{"reservationUid": "x"}]
        loy_resp = MagicMock(status_code=200)
        loy_resp.json.return_value = {"status": "GOLD", "discount": 10, "reservationCount": 25}
        mock_get.side_effect = [res_resp, loy_resp]
        r = self.client.get("/api/v1/me", headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["loyalty"]["status"], "GOLD")
        self.assertEqual(len(body["reservations"]), 1)

    @patch("gateway.requests.get")
    def test_get_me_no_header(self, mock_get):
        r = self.client.get("/api/v1/me")
        self.assertEqual(r.status_code, 400)

    @patch("gateway.requests.get")
    def test_get_me_loyalty_404(self, mock_get):
        res_resp = MagicMock(status_code=200)
        res_resp.json.return_value = []
        loy_resp = MagicMock(status_code=404)
        loy_resp.json.return_value = {"message": "User not found"}
        mock_get.side_effect = [res_resp, loy_resp]
        r = self.client.get("/api/v1/me", headers={"X-User-Name": "Unknown"})
        self.assertEqual(r.status_code, 404)

    @patch("gateway.requests.request")
    def test_create_reservation_proxies(self, mock_req):
        resp = MagicMock(status_code=200, content=b"{}")
        resp.json.return_value = {"reservationUid": "r", "status": "PAID",
                                  "payment": {"status": "PAID", "price": 27000}}
        mock_req.return_value = resp
        r = self.client.post(
            "/api/v1/reservations",
            headers={"X-User-Name": "Test Max"},
            json={"hotelUid": "049161bb-badd-4fa8-9d90-87c9a82b0668",
                  "startDate": "2021-10-08", "endDate": "2021-10-11"},
        )
        self.assertEqual(r.status_code, 200)
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], "POST")
        self.assertTrue(args[1].endswith("/api/v1/reservations"))
        self.assertEqual(kwargs["headers"].get("X-User-Name"), "Test Max")

    @patch("gateway.requests.request")
    def test_delete_proxies(self, mock_req):
        resp = MagicMock(status_code=204, content=b"")
        mock_req.return_value = resp
        r = self.client.delete(
            "/api/v1/reservations/9b4ba1f7-e5ac-465b-ace4-7b54dec20f9a",
            headers={"X-User-Name": "Test Max"},
        )
        self.assertEqual(r.status_code, 204)

    @patch("gateway.requests.request")
    def test_internal_loyalty_increment(self, mock_req):
        resp = MagicMock(status_code=200, content=b"{}")
        resp.json.return_value = {"status": "GOLD", "discount": 10, "reservationCount": 26}
        mock_req.return_value = resp
        r = self.client.post("/api/v1/internal/loyalty/increment",
                             headers={"X-User-Name": "Test Max"})
        self.assertEqual(r.status_code, 200)
        args, kwargs = mock_req.call_args
        self.assertTrue(args[1].endswith("/api/v1/loyalty/increment"))


if __name__ == "__main__":
    unittest.main()
