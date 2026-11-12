#!/usr/bin/env python3
"""Small loopback-only A2A JSON-RPC and SSE server."""

from __future__ import annotations

import json
import os
import hmac
import secrets
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any, Dict, Optional

from core.a2a_protocol import build_agent_card, format_agent_to_user_response


TERMINAL_STATES = {"completed", "failed", "canceled"}


class _A2AHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, owner: "A2AServer", port: int):
        super().__init__(("127.0.0.1", port), _A2ARequestHandler)
        self.owner = owner


class _A2ARequestHandler(BaseHTTPRequestHandler):
    server: _A2AHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def owner(self) -> "A2AServer":
        return self.server.owner

    def _authorized(self) -> bool:
        token = self.owner.token
        if not token:
            return True
        return hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")

    def _send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reject_auth(self) -> None:
        self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)

    def do_GET(self) -> None:
        if not self._authorized():
            self._reject_auth()
            return
        path = urlparse(self.path)
        if path.path == "/.well-known/agent.json":
            self._send_json(build_agent_card())
        elif path.path == "/a2a/stream":
            task_id = parse_qs(path.query).get("task_id", [None])[0]
            self.owner.stream(self, task_id)
        else:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            self._reject_auth()
            return
        if urlparse(self.path).path != "/a2a":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1024 * 1024:
                raise ValueError("request body too large")
            request = json.loads(self.rfile.read(length))
            response = self.owner.dispatch(request)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": str(exc)}}
        self._send_json(response)


class A2AServer:
    """Threaded, in-memory A2A server bound exclusively to loopback."""

    def __init__(self, port: int = 8090, token: Optional[str] = None, assistant: Any = None, max_tasks: int = 64):
        if not 0 <= int(port) <= 65535:
            raise ValueError("port must be between 0 and 65535")
        self.token = token or os.getenv("NOVA_A2A_TOKEN") or secrets.token_urlsafe(32)
        self.max_tasks = max(1, int(max_tasks))
        self.assistant = assistant
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, list[Dict[str, Any]]] = {}
        self._condition = threading.Condition(threading.RLock())
        self._cancel_events: Dict[str, threading.Event] = {}
        self.httpd = _A2AHTTPServer(self, int(port))

    @property
    def server_address(self):
        return self.httpd.server_address

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()

    def server_close(self) -> None:
        self.httpd.server_close()

    def _snapshot(self, task_id: str) -> Dict[str, Any]:
        with self._condition:
            return json.loads(json.dumps(self._tasks[task_id]))

    def _emit(self, task_id: str, state: str, text: str = "") -> None:
        task = self._tasks[task_id]
        response = format_agent_to_user_response(task_id, text, job_status={
            "submitted": "QUEUED", "working": "RUNNING", "completed": "COMPLETE",
            "failed": "FAILED", "canceled": "BLOCKED",
        }[state])
        task["status"] = response["status"]
        task["status"]["state"] = state
        task["artifacts"] = response["artifacts"]
        self._events[task_id].append(self._snapshot(task_id))
        self._condition.notify_all()

    def _run_task(self, task_id: str, text: str) -> None:
        with self._condition:
            if self._tasks[task_id]["status"]["state"] == "canceled":
                return
            self._emit(task_id, "working", "Task is running")
        try:
            assistant = self.assistant
            if assistant is None:
                from voice.assistant import NovaVoiceAssistant
                assistant = NovaVoiceAssistant(allow_shell=False, allow_mac_control=False)
            try:
                result = assistant.process_command(
                    text,
                    voice_output=False,
                    cancel_event=self._cancel_events[task_id],
                )
            except TypeError:
                result = assistant.process_command(text, voice_output=False)
            with self._condition:
                if self._tasks[task_id]["status"]["state"] != "canceled":
                    self._emit(task_id, "completed", str(result))
        except Exception as exc:
            with self._condition:
                if self._tasks[task_id]["status"]["state"] != "canceled":
                    self._emit(task_id, "failed", str(exc))

    @staticmethod
    def _text_from_params(params: Dict[str, Any]) -> str:
        message = params.get("message", {})
        parts = message.get("parts", []) if isinstance(message, dict) else []
        text = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        value = "\n".join(str(item) for item in text).strip()
        if not value:
            raise ValueError("params.message.parts must contain a text part")
        return value

    def dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if request.get("jsonrpc") != "2.0" or "id" not in request:
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}
        req_id = request["id"]
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "params must be an object"}}
        try:
            if method == "message/send":
                task_id = str(params.get("id") or f"task-{uuid.uuid4().hex[:12]}")
                text = self._text_from_params(params)
                with self._condition:
                    if task_id in self._tasks:
                        raise ValueError(f"task already exists: {task_id}")
                    terminal = [tid for tid, task in self._tasks.items() if task["status"]["state"] in TERMINAL_STATES]
                    if len(self._tasks) >= self.max_tasks and not terminal:
                        raise ValueError("A2A task capacity is full")
                    if terminal:
                        old_id = terminal[0]
                        self._tasks.pop(old_id, None)
                        self._events.pop(old_id, None)
                        self._cancel_events.pop(old_id, None)
                    self._tasks[task_id] = {"id": task_id, "status": {"state": "submitted"}, "artifacts": []}
                    self._events[task_id] = []
                    self._cancel_events[task_id] = threading.Event()
                    self._emit(task_id, "submitted", "Task accepted")
                threading.Thread(target=self._run_task, args=(task_id, text), daemon=True).start()
                result = self._snapshot(task_id)
            elif method == "tasks/get":
                task_id = str(params["id"])
                result = self._snapshot(task_id)
            elif method == "tasks/cancel":
                task_id = str(params["id"])
                with self._condition:
                    if task_id not in self._tasks:
                        raise KeyError(task_id)
                    if self._tasks[task_id]["status"]["state"] in TERMINAL_STATES:
                        result = self._snapshot(task_id)
                        return {"jsonrpc": "2.0", "id": req_id, "result": result}
                    self._cancel_events[task_id].set()
                    self._emit(task_id, "canceled", "Task canceled")
                    result = self._snapshot(task_id)
            else:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except (KeyError, ValueError) as exc:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": str(exc)}}

    def stream(self, handler: _A2ARequestHandler, task_id: Optional[str]) -> None:
        if not task_id or task_id not in self._tasks:
            handler._send_json({"error": "task_not_found"}, HTTPStatus.NOT_FOUND)
            return
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        index = 0
        while True:
            with self._condition:
                while index >= len(self._events[task_id]):
                    if self._tasks[task_id]["status"]["state"] in TERMINAL_STATES:
                        return
                    self._condition.wait(timeout=1.0)
                    if index >= len(self._events[task_id]) and self._tasks[task_id]["status"]["state"] in TERMINAL_STATES:
                        return
                event = self._events[task_id][index]
                index += 1
            payload = f"event: task\ndata: {json.dumps(event, separators=(',', ':'))}\n\n".encode()
            try:
                handler.wfile.write(payload)
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


def serve_a2a(port: int = 8090) -> None:
    server = A2AServer(port=port)
    print(f"Nova-Claw A2A server listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
