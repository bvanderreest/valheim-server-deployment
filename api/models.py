from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    model_config = ConfigDict(populate_by_name=True)

    # Identity
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

    # Server-specific extras not covered by the standard shape
    extras: dict

    # Legacy top-level fields preserved for backward-compat consumers.
    # serialization_alias ensures the JSON key is "_deprecated" while the
    # Python attribute remains a valid identifier.
    deprecated: dict = Field(serialization_alias="_deprecated")


class ActionResponse(BaseModel):
    action: str
    accepted: bool
    message: str


class LogsResponse(BaseModel):
    lines: list[str]
    count: int
    log_file: str
