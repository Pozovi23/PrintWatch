"""Configuration management loading settings and N printers from config/printers.yaml."""

from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrinterConfig(BaseModel):
    """Configuration for an individual 3D printer loaded from YAML."""

    name: str = Field(..., description="Unique identifier for metrics label")
    host: str = Field(..., description="Base URL or IP address")
    api_key: Optional[SecretStr] = Field(default=None, description="Optional API key")

    @field_validator("host")
    @classmethod
    def normalize_host(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            v = f"http://{v}"
        return v


def load_yaml_config(filepath: str | Path) -> tuple[float, list[PrinterConfig]]:
    """Load global settings and printer definitions strictly from a YAML file."""
    path = Path(filepath)
    if not path.is_file():
        # Also check relative to project root (2 levels up from services/printer-exporter)
        project_root = Path(__file__).resolve().parents[2]
        alt_path = project_root / filepath
        if alt_path.is_file():
            path = alt_path
        else:
            fallback_path = Path("config/printers.yaml.example")
            if not fallback_path.is_file():
                fallback_path = project_root / "config/printers.yaml.example"
            if fallback_path.is_file():
                path = fallback_path
            else:
                return 5.0, []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

            # Read poll_interval from settings section
            settings_block = data.get("settings", {})
            poll_interval = float(settings_block.get("poll_interval", 5.0))

            # Read printers list
            items = data.get("printers", [])
            configs: list[PrinterConfig] = []
            for item in items:
                if isinstance(item, dict) and item.get("host"):
                    if item.get("api_key"):
                        item["api_key"] = SecretStr(str(item["api_key"]))
                    configs.append(PrinterConfig(**item))
            return poll_interval, configs
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return 5.0, []


class Settings(BaseSettings):
    """Global exporter settings."""

    poll_interval: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="Polling interval in seconds (loaded from printers.yaml settings)",
    )
    port: int = Field(
        default=9108,
        ge=1024,
        le=65535,
        description="Port for Prometheus HTTP metrics endpoint",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    timeout_seconds: float = Field(
        default=3.5,
        ge=1.0,
        le=30.0,
        description="HTTP request timeout in seconds",
    )
    config_file: str = Field(
        default="config/printers.yaml",
        description="Path to printers.yaml config file",
    )

    printers: list[PrinterConfig] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="EXPORTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def load_all_printers(self) -> list[PrinterConfig]:
        """Load poll_interval and printers from the YAML configuration file."""
        poll_interval, printers = load_yaml_config(self.config_file)
        self.poll_interval = poll_interval
        self.printers = printers
        return printers
