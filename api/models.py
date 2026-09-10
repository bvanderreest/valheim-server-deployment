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
    # Follow it at /v1/jobs/{job_id}/stream. Optional so the field can be absent
    # rather than a lie if an action is ever handled without a job.
    job_id: Optional[str] = None


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


class StallEvent(BaseModel):
    """One main-thread freeze, placed in time."""

    kind: str  # "save" | "gc"
    epoch: float
    ms: float
    # False for GC events: Unity writes those lines with no timestamp, so the
    # time is inferred from the last timestamped line above. Surfaced rather
    # than hidden — a timeline that implies precision it lacks is worse than
    # one that admits the estimate.
    exact: bool
    total_ms: Optional[float] = None  # save only: wall time incl. background I/O
    objects: Optional[int] = None  # gc only: loaded objects scanned


class StallSummary(BaseModel):
    count: int
    per_hour: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    max_ms: Optional[float] = None
    total_ms: float
    last_epoch: Optional[float] = None


class StallContext(BaseModel):
    world_zdos: Optional[int] = None
    loaded_objects: Optional[int] = None
    players: Optional[int] = None
    net_sent_bytes: Optional[int] = None
    net_recv_bytes: Optional[int] = None


class FindingEvidence(BaseModel):
    label: str
    value: str
    # A timestamp is sent as an epoch, never pre-formatted: the server is in AU
    # and half the group is not, so the reader's browser has to render it.
    epoch: Optional[float] = None


class Finding(BaseModel):
    """A judgement with the numbers that produced it.

    `evidence` is not decoration: a reader has to be able to disagree with the
    verdict and still use the measurement. `method` says how it was judged, so
    an inferred claim can never be mistaken for a measured one.
    """

    domain: str  # "hardware" | "network" | "configuration"
    id: str
    verdict: str  # "problem" | "watch" | "ok" | "unknown"
    headline: str
    evidence: list[FindingEvidence]
    method: str


class PerformanceResponse(BaseModel):
    generated_at: float
    window_hours: float
    log_file: str
    # The part of the window the log actually covers. Rates are computed over
    # THIS, not over window_hours — a server restarted ten minutes ago has been
    # observed for ten minutes, not six hours.
    log_covers_from: Optional[float] = None
    log_covers_to: Optional[float] = None
    observed_hours: float
    truncated: bool
    events: list[StallEvent]
    save: StallSummary
    gc: StallSummary
    blocked_ms: float
    blocked_ms_per_hour: Optional[float] = None
    blocked_pct: Optional[float] = None
    save_interval_s: Optional[int] = None
    context: StallContext
    findings: list[Finding] = []
    log_files_read: int = 1


class JobStage(BaseModel):
    key: str
    label: str
    state: str  # pending | active | done | failed | skipped
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    detail: Optional[str] = None
    percent: Optional[float] = None


class JobSummary(BaseModel):
    id: str
    action: str
    state: str  # running | succeeded | failed | killed
    started_at: float
    ended_at: Optional[float] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    line_count: int
    stages: list[JobStage] = []


class JobDetail(JobSummary):
    lines: list[str] = []
    # True when the line cap dropped earlier output — so the console can say
    # "earlier lines dropped" rather than implying it has the whole run.
    truncated: bool = False


class JobList(BaseModel):
    jobs: list[JobSummary] = []
