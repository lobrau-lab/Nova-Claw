#!/usr/bin/env python3
"""
DeepClaw Nova - Google Agent2Agent (A2A) & ADK Communication Protocol
Implements Google Developer recommendations for:
1. Agent-to-Agent (A2A) interoperability: AgentCard (/.well-known/agent.json),
   JSON-RPC 2.0 envelopes (message/send, tasks/send, tasks/get, tasks/cancel),
   and typed message parts (TextPart, FilePart, DataPart).
2. User-to-Agent (U2A) sanitization: explicit separation of user intent parts
   from untrusted tool/file data parts.
3. Agent-to-User (A2U) structured responses: observable artifacts, explicit
   task lifecycle states (submitted, working, input-required, completed, failed, canceled),
   and grounded status reporting.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Literal
import config


A2ATaskState = Literal[
    "submitted",
    "working",
    "input-required",
    "completed",
    "canceled",
    "failed",
    "unknown",
]

JOB_TO_A2A_STATE: Dict[str, A2ATaskState] = {
    "QUEUED": "submitted",
    "VALIDATING": "working",
    "WAITING_RESOURCE": "working",
    "RUNNING": "working",
    "VALIDATING_OUTPUT": "working",
    "RECOVERING": "working",
    "PAUSED": "input-required",
    "COMPLETE": "completed",
    "FAILED": "failed",
    "BLOCKED": "input-required",
}


@dataclass
class TextPart:
    text: str
    type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text, **({"metadata": self.metadata} if self.metadata else {})}


@dataclass
class FilePart:
    uri: str
    name: str = ""
    mime_type: str = "text/plain"
    type: str = "file"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "file",
            "file": {"uri": self.uri, "name": self.name, "mimeType": self.mime_type},
        }


@dataclass
class DataPart:
    data: Dict[str, Any]
    type: str = "data"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "data", "data": self.data}


def build_agent_card(skills: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Builds a Google A2A-compliant AgentCard (/.well-known/agent.json schema).
    Describes identity, supported modalities, authentication, and skills.
    """
    skill_entries = []
    for s in skills or []:
        fn = s.get("function", s)
        skill_entries.append({
            "id": fn.get("name", "unknown"),
            "name": fn.get("name", "unknown"),
            "description": fn.get("description", ""),
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["text/plain", "application/json"],
        })
    return {
        "name": "DeepClaw Nova",
        "description": "Local Apple Silicon M5 Autonomous Coding, Voice & Computer-Control Agent",
        "url": "http://127.0.0.1:8000",
        "version": "2.1.0",
        "protocolVersion": "0.2.5",
        "provider": {"organization": "DeepClaw Local", "url": "http://127.0.0.1"},
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "authentication": {"schemes": ["Bearer"]},
        "defaultInputModes": ["text/plain", "application/json", "audio/wav"],
        "defaultOutputModes": ["text/plain", "application/json", "audio/wav"],
        "skills": skill_entries,
    }


def format_user_to_agent_message(
    user_text: str,
    context_memories: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Structures User-to-Agent (U2A) input following Google ADK / A2A Part separation:
    keeps primary user instruction in a TextPart and isolates untrusted context/files
    into explicit DataPart/FilePart structures.
    """
    parts: List[Dict[str, Any]] = [TextPart(text=user_text.strip()).to_dict()]
    if context_memories:
        parts.append(DataPart(data={"untrusted_memory_context": context_memories}).to_dict())
    for fp in files or []:
        parts.append(FilePart(uri=str(fp), name=str(fp).split("/")[-1]).to_dict())
    return {
        "messageId": f"msg-{uuid.uuid4().hex[:12]}",
        "role": "user",
        "parts": parts,
        "timestamp": time.time(),
    }


def format_agent_to_user_response(
    task_id: str,
    text: str,
    job_status: str = "COMPLETE",
    artifacts: Optional[List[str]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Structures Agent-to-User (A2U) output with explicit A2A lifecycle state,
    TextPart response, FilePart artifacts, and execution telemetry DataPart.
    """
    state: A2ATaskState = JOB_TO_A2A_STATE.get(job_status.upper(), "unknown")
    parts: List[Dict[str, Any]] = [TextPart(text=text).to_dict()]
    artifact_objs = []
    for path_str in artifacts or []:
        artifact_objs.append({
            "artifactId": f"art-{uuid.uuid4().hex[:8]}",
            "name": str(path_str).split("/")[-1],
            "parts": [FilePart(uri=f"file://{path_str}", name=str(path_str).split("/")[-1]).to_dict()],
        })
    if metrics:
        parts.append(DataPart(data={"telemetry": metrics}).to_dict())
    return {
        "id": task_id,
        "status": {
            "state": state,
            "message": {
                "role": "agent",
                "parts": parts,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "artifacts": artifact_objs,
    }


def build_a2a_jsonrpc_request(
    method: str,
    task_id: str,
    role: str,
    text: str,
    data: Optional[Dict[str, Any]] = None,
    req_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs a Google A2A JSON-RPC 2.0 request envelope for Agent-to-Agent (A2A)
    delegation (e.g., 'message/send', 'tasks/send', 'tasks/get', 'tasks/cancel').
    """
    parts: List[Dict[str, Any]] = [TextPart(text=text).to_dict()]
    if data:
        parts.append(DataPart(data=data).to_dict())
    return {
        "jsonrpc": "2.0",
        "id": req_id or f"rpc-{uuid.uuid4().hex[:10]}",
        "method": method,
        "params": {
            "id": task_id,
            "message": {
                "role": role,
                "parts": parts,
            },
        },
    }
