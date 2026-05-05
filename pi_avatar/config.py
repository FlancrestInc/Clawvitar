from dataclasses import dataclass
from pathlib import Path

from .constants import (
    CONFIG_AUDIT_LOG,
    DEFAULT_ASSET_DIR,
    DEFAULT_ENV_FILE,
    DEFAULT_STATE_FILE,
    DEFAULT_STATUS_BIND_HOST,
    DEFAULT_STATUS_BIND_PORT,
    DEFAULT_STATUS_URL,
    HTTP_TIMEOUT_SECONDS,
    OPENCLAW_PORT,
    OPENCLAW_SERVICE,
    RUNTIME_LOG,
    STALE_STATUS_SECONDS,
)


@dataclass(frozen=True)
class Config:
    state_file: Path = DEFAULT_STATE_FILE
    asset_dir: Path = DEFAULT_ASSET_DIR
    env_file: Path = DEFAULT_ENV_FILE
    status_url: str = DEFAULT_STATUS_URL
    status_bind_host: str = DEFAULT_STATUS_BIND_HOST
    status_bind_port: int = DEFAULT_STATUS_BIND_PORT
    http_timeout_seconds: float = HTTP_TIMEOUT_SECONDS
    stale_status_seconds: float = STALE_STATUS_SECONDS
    openclaw_service: str = OPENCLAW_SERVICE
    openclaw_port: str = OPENCLAW_PORT
    runtime_log: Path = RUNTIME_LOG
    config_audit_log: Path = CONFIG_AUDIT_LOG


def _get_path(env, key, default):
    return Path(env.get(key, str(default)))


def _get_int(env, key, default):
    raw = env.get(key)
    if raw in (None, ""):
        return default
    return int(raw)


def _get_float(env, key, default):
    raw = env.get(key)
    if raw in (None, ""):
        return default
    return float(raw)


def load_config(env=None):
    env = env or {}

    return Config(
        state_file=_get_path(env, "STATE_FILE", DEFAULT_STATE_FILE),
        asset_dir=_get_path(env, "ASSET_DIR", DEFAULT_ASSET_DIR),
        env_file=_get_path(env, "ENV_FILE", DEFAULT_ENV_FILE),
        status_url=env.get("STATUS_URL", DEFAULT_STATUS_URL),
        status_bind_host=env.get("STATUS_BIND_HOST", DEFAULT_STATUS_BIND_HOST),
        status_bind_port=_get_int(env, "STATUS_BIND_PORT", DEFAULT_STATUS_BIND_PORT),
        http_timeout_seconds=_get_float(env, "HTTP_TIMEOUT_SECONDS", HTTP_TIMEOUT_SECONDS),
        stale_status_seconds=_get_float(env, "STALE_STATUS_SECONDS", STALE_STATUS_SECONDS),
        openclaw_service=env.get("OPENCLAW_SERVICE", OPENCLAW_SERVICE),
        openclaw_port=env.get("OPENCLAW_PORT", OPENCLAW_PORT),
        runtime_log=_get_path(env, "OPENCLAW_RUNTIME_LOG", RUNTIME_LOG),
        config_audit_log=_get_path(env, "OPENCLAW_CONFIG_AUDIT_LOG", CONFIG_AUDIT_LOG),
    )
