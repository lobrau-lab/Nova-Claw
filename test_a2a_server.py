import json
import threading
import unittest
from http.client import HTTPConnection
from urllib.parse import urlencode

from core.a2a_server import A2AServer


class _FakeAssistant:
    def process_command(self, text, voice_output=False):
        return f"handled: {text}"


class _CancelableAssistant:
    def process_command(self, text, voice_output=False, cancel_event=None):
        while cancel_event and not cancel_event.is_set():
            cancel_event.wait(0.01)
        return "canceled"


class A2AServerTests(unittest.TestCase):
    def setUp(self):
        self.server = A2AServer(port=0, token="test-token", assistant=_FakeAssistant())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, token="test-token"):
        conn = HTTPConnection(self.host, self.port, timeout=3)
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(payload))
        else:
            payload = None
        conn.request(method, path, payload, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, response.getheader("Content-Type", ""), data

    def test_agent_card_is_served(self):
        status, content_type, body = self.request("GET", "/.well-known/agent.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body)["protocolVersion"], "0.2.5")

    def test_jsonrpc_dispatch_and_task_lifecycle(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "hello"}]}},
        }
        status, _, body = self.request("POST", "/a2a", request)
        self.assertEqual(status, 200)
        result = json.loads(body)["result"]
        task_id = result["id"]
        self.assertIn(result["status"]["state"], {"submitted", "working", "completed"})

        status, _, body = self.request(
            "POST", "/a2a", {"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task_id}}
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["id"], task_id)

    def test_sse_streams_terminal_event(self):
        request = {
            "jsonrpc": "2.0",
            "id": "stream",
            "method": "message/send",
            "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "stream me"}]}},
        }
        _, _, body = self.request("POST", "/a2a", request)
        task_id = json.loads(body)["result"]["id"]

        conn = HTTPConnection(self.host, self.port, timeout=3)
        conn.request("GET", f"/a2a/stream?{urlencode({'task_id': task_id})}", headers={"Authorization": "Bearer test-token"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        chunks = []
        while True:
            line = response.readline()
            if not line:
                break
            chunks.append(line.decode())
            if '"state":"completed"' in "".join(chunks):
                break
        conn.close()
        stream = "".join(chunks)
        self.assertIn("text/event-stream", response.getheader("Content-Type", ""))
        self.assertIn('"state":"completed"', stream)

    def test_invalid_token_is_rejected(self):
        status, _, _ = self.request("GET", "/.well-known/agent.json", token="wrong")
        self.assertEqual(status, 401)

    def test_malformed_params_are_rejected(self):
        status, _, body = self.request("POST", "/a2a", {
            "jsonrpc": "2.0", "id": 3, "method": "tasks/get", "params": []
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32602)

    def test_cancel_sets_terminal_state_and_stops_worker(self):
        self.server.assistant = _CancelableAssistant()
        request = {
            "jsonrpc": "2.0", "id": "cancel", "method": "message/send",
            "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "wait"}]}},
        }
        _, _, body = self.request("POST", "/a2a", request)
        task_id = json.loads(body)["result"]["id"]
        status, _, body = self.request("POST", "/a2a", {
            "jsonrpc": "2.0", "id": "cancel-2", "method": "tasks/cancel", "params": {"id": task_id}
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["status"]["state"], "canceled")

    def test_default_server_requires_a_generated_token(self):
        server = A2AServer(port=0, assistant=_FakeAssistant())
        try:
            self.assertTrue(server.token)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            conn = HTTPConnection(host, port, timeout=3)
            conn.request("GET", "/.well-known/agent.json")
            self.assertEqual(conn.getresponse().status, 401)
            conn.close()
            server.shutdown()
            thread.join(timeout=2)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
