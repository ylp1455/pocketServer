import json
import shutil
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

from pocketserver.auth import verify_password
from pocketserver.server import PocketRequestHandler, PocketServer


class AdminHttpTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        self.app = PocketServer(self.data_dir, "127.0.0.1", 0)
        app = self.app

        class Handler(PocketRequestHandler):
            server_app = app

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.app.metadata.close()
        shutil.rmtree(self.data_dir)

    def request(self, path, method="GET", payload=None, headers=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=request_headers, method=method
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_client_admin_and_password_change_flow(self):
        with self.request("/") as response:
            client_page = response.read()
            self.assertIn(b"Recently added", client_page)
            self.assertNotIn(b'data-library-filter="series"', client_page)
        with self.request("/admin") as response:
            self.assertIn(b"SERVER ADMINISTRATION", response.read())

        with self.request(
            "/api/requests",
            method="POST",
            payload={"title": "Arrival", "type": "movie", "year": "2016", "requested_by": "Sam"},
        ) as response:
            requested = json.load(response)["request"]
            self.assertEqual(201, response.status)
            self.assertEqual("pending", requested["status"])

        with self.assertRaises(urllib.error.HTTPError) as private_queue:
            self.request("/api/requests")
        self.assertEqual(401, private_queue.exception.code)

        with self.assertRaises(urllib.error.HTTPError) as unauthorized:
            self.request("/api/status")
        self.assertEqual(401, unauthorized.exception.code)

        with self.request(
            "/api/auth/login",
            method="POST",
            payload={"username": "admin", "password": "admin"},
        ) as response:
            login = json.load(response)
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(login["authenticated"])
        self.assertTrue(login["must_change_password"])

        auth_headers = {"Cookie": cookie, "X-CSRF-Token": login["csrf_token"]}
        with self.request("/api/requests", headers=auth_headers) as response:
            requests = json.load(response)["items"]
        self.assertEqual("Arrival", requests[0]["title"])

        with self.request(
            f"/api/requests/{requested['id']}/status",
            method="POST",
            payload={"status": "approved"},
            headers=auth_headers,
        ) as response:
            self.assertEqual("approved", json.load(response)["request"]["status"])

        with self.request(
            "/api/settings/metadata",
            method="POST",
            payload={"enabled": False, "api_key": "test-key"},
            headers=auth_headers,
        ) as response:
            metadata = json.load(response)["metadata"]
        self.assertTrue(metadata["enabled"])
        self.assertTrue(metadata["configured"])

        with self.request(
            "/api/auth/password",
            method="POST",
            payload={"current_password": "admin", "new_password": "new-password-123"},
            headers=auth_headers,
        ) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertTrue(verify_password("new-password-123", self.app.config["auth"]))
        self.assertFalse(self.app.config["auth"]["must_change_password"])


if __name__ == "__main__":
    unittest.main()
