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


class ConfigResponse(BaseModel):
    server_type: str
    server_label: str
    config: dict[str, str]
    config_file: str
    editable_keys: list[str]


class ConfigUpdateRequest(BaseModel):
    changes: dict[str, str]


class ConfigUpdateResponse(BaseModel):
    applied: dict[str, str]
    restart_required: bool


class ModInfo(BaseModel):
    package_id: str
    name: str
    version: str
    enabled: bool
    description: Optional[str] = None
    website_url: Optional[str] = None
    installed_at: str
    source: Optional[str] = None


class ModsResponse(BaseModel):
    mods: list[ModInfo]
    count: int
    mod_dir: str


class ModInstallRequest(BaseModel):
    source_url: str
    package_id: Optional[str] = None  # auto-derived from URL if omitted


class ModInstallResponse(BaseModel):
    package_id: str
    name: str
    version: str
    installed: bool
    message: str


class ModActionResponse(BaseModel):
    package_id: str
    action: str  # "enabled" | "disabled" | "deleted"
    success: bool
    message: str
