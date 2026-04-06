from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API enable guard — must be explicitly set to true in .env
    api_enabled: bool = False

    # API network binding
    api_port: int = 8080
    api_host: str = "127.0.0.1"

    # Auth — comma-separated keys, e.g. "key1,key2"
    api_keys: str = ""

    # CORS — comma-separated origins (e.g. "https://dashboard.example.com").
    # No default: operators must explicitly allow their dashboard origin.
    cors_origins: str = ""

    # Set to true to expose /docs and /redoc (disable in production)
    api_docs_enabled: bool = False

    # Server identity (shown in every response so the dashboard knows which server this is)
    server_type: str = "valheim"
    server_label: str = "Valheim Server"

    # Server info read from existing .env
    server_name: str = "My-Server"
    world_name: str = "My-World"
    port: int = 2456
    crossplay: str = "true"
    public: str = "0"
    max_players: int = 10

    # Paths — read LOG_DIR and PIDFILE from existing .env; logfile is derived
    log_dir: Path = Path("/srv/valheim/logs")
    pidfile: Path = Path("/srv/valheim/valheim.pid")

    # logfile is computed from log_dir unless explicitly overridden via LOGFILE_OVERRIDE
    logfile_override: Optional[Path] = None

    @model_validator(mode="after")
    def resolve_logfile(self) -> "Settings":
        if self.logfile_override is None:
            self._logfile = self.log_dir / "valheim-server.log"
        else:
            self._logfile = self.logfile_override
        return self

    @property
    def logfile(self) -> Path:
        return self._logfile

    @property
    def api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def script_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def manager_script(self) -> Path:
        return self.script_dir / "valheim-server-manager.sh"

    # Mod management — optional overrides; derived from script_dir/server/BepInEx/ by default
    mod_dir_override: Optional[Path] = None
    mod_disabled_dir_override: Optional[Path] = None
    mod_trash_dir_override: Optional[Path] = None
    # Comma-separated hostnames allowed as mod download sources
    mod_allowed_sources: str = "thunderstore.io,gcdn.thunderstore.io"
    # Maximum archive size in megabytes accepted by POST /mods/install
    mod_max_size_mb: int = 100

    @property
    def mod_dir(self) -> Path:
        return self.mod_dir_override or (self.script_dir / "server" / "BepInEx" / "plugins")

    @property
    def mod_disabled_dir(self) -> Path:
        return self.mod_disabled_dir_override or (self.script_dir / "server" / "BepInEx" / "plugins_disabled")

    @property
    def mod_trash_dir(self) -> Path:
        return self.mod_trash_dir_override or (self.script_dir / "server" / "BepInEx" / "plugins_trash")

    @property
    def mod_allowed_sources_list(self) -> list[str]:
        return [s.strip() for s in self.mod_allowed_sources.split(",") if s.strip()]

    model_config = {
        "env_file": Path(__file__).parent.parent / ".env",
        "env_file_encoding": "utf-8",
        # Ignore bash-specific vars (SERVER_DIR, BINARY, SAVE_INTERVAL, etc.)
        "extra": "ignore",
    }


settings = Settings()
