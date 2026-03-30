from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    server_type: str
    server_label: str


class PlayerInfo(BaseModel):
    count: int
    max: int
    names: list[str]


class ConnectionInfo(BaseModel):
    ip: str
    port: int
    join_code: Optional[str]
    crossplay: bool
    public: bool


class StatusResponse(BaseModel):
    # Identity — lets the dashboard know which server this is
    server_type: str
    server_label: str
    server_name: str
    world_name: str

    # Process state
    running: bool
    pid: Optional[int]
    uptime_seconds: int
    uptime_human: str

    # Game info (only populated when running)
    version: Optional[str]
    players: PlayerInfo
    connection: ConnectionInfo
    last_save: Optional[str]


class ActionResponse(BaseModel):
    accepted: bool
    message: str


class LogsResponse(BaseModel):
    lines: list[str]
    total_lines: int
    logfile: str
