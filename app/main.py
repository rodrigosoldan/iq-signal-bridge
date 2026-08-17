"""Read-only IQ Signal bridge.

This service intentionally exposes no order placement or trade-management routes.
"""
from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

APP_KEY = os.environ.get("BRIDGE_API_KEY", "")
if not APP_KEY:
    raise RuntimeError("BRIDGE_API_KEY must be configured")

app = FastAPI(title="IQ Signal Bridge", version="1.0.0", docs_url=None, redoc_url=None)
_lock = threading.RLock()
_sessions: dict[str, "Session"] = {}


def authorize(key: str | None) -> None:
    if not key or not secrets.compare_digest(key, APP_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")


def iq_client(email: str, password: str):
    # iqoptionapi is an unofficial, read-only data connection here. No order API is used.
    from iqoptionapi.stable_api import IQ_Option
    client = IQ_Option(email, password)
    ok, reason = client.connect()
    if not ok:
        raise HTTPException(status_code=401, detail=f"IQ Option login failed: {reason}")
    return client


@dataclass
class Session:
    client: Any
    mode: str = "PRACTICE"


class Login(BaseModel):
    email: str
    password: str


class SessionRequest(BaseModel):
    session_id: str


class ModeRequest(SessionRequest):
    mode: str


class CandleRequest(SessionRequest):
    active: str = Field(pattern=r"^[A-Z0-9_-]{2,24}$")
    size: int = Field(default=60, ge=60, le=60)
    count: int = Field(default=100, ge=2, le=500)


def get_session(session_id: str) -> Session:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return session


def set_mode(session: Session, mode: str) -> None:
    normalized = mode.upper()
    if normalized not in {"PRACTICE", "REAL"}:
        raise HTTPException(status_code=400, detail="mode must be PRACTICE or REAL")
    # Change balance only. This is not an order-placement operation.
    session.client.change_balance("PRACTICE" if normalized == "PRACTICE" else "REAL")
    session.mode = normalized


@app.post("/v1/ping")
def ping(x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    return {"ok": True, "service": "iq-signal-bridge", "read_only": True}


@app.post("/v1/login")
def login(payload: Login, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        client = iq_client(payload.email, payload.password)
        client.change_balance("PRACTICE")
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = Session(client=client)
    return {"session_id": session_id, "mode": "PRACTICE", "read_only": True}


@app.post("/v1/mode")
def mode(payload: ModeRequest, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        session = get_session(payload.session_id)
        set_mode(session, payload.mode)
    return {"mode": session.mode, "read_only": True}


@app.post("/v1/account")
def account(payload: SessionRequest, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        session = get_session(payload.session_id)
        return {"mode": session.mode, "balance": session.client.get_balance(), "read_only": True}


@app.post("/v1/candles")
def candles(payload: CandleRequest, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        session = get_session(payload.session_id)
        active_id = session.client.get_active_id_by_name(payload.active)
        if not active_id:
            raise HTTPException(status_code=404, detail="Asset unavailable")
        data = session.client.get_candles(active_id, payload.size, payload.count, __import__("time").time())
    return {"asset": payload.active, "size": payload.size, "candles": data, "read_only": True}


@app.post("/v1/open-actives")
def open_actives(payload: SessionRequest, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        session = get_session(payload.session_id)
        return {"actives": session.client.get_all_open_time(), "read_only": True}


@app.post("/v1/logout")
def logout(payload: SessionRequest, x_bridge_key: str | None = Header(default=None)):
    authorize(x_bridge_key)
    with _lock:
        _sessions.pop(payload.session_id, None)
    return {"ok": True}
