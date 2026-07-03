import os
from dataclasses import dataclass, field
from typing import Any

import yaml


class ConfigError(Exception):
    pass


@dataclass
class MimirConfig:
    """Mimir runtime configuration.

    Gain defaults (lna=24.0, vga=26.0) are calibrated for the telescopic
    whip SMA antenna (~1 GHz optimised). Poor coupling at FM wavelengths
    requires gain to compensate. Confirmed safe on live hardware with
    Adelaide FM signals (no ADC saturation).
    """
    frequencies_hz: list[float] = field(default_factory=lambda: [98_000_000, 145_175_000, 915_000_000, 1_090_000_000])
    dwell_time_sec: float = 2.0
    num_samples: int = 2_000_000
    lna_gain_db: float = 24.0
    vga_gain_db: float = 26.0
    amp_enable: bool = False
    queue_maxsize: int = 20
    llm_url: str = "http://192.168.0.66:8080/v1"
    llm_cooldown_sec: float = 60.0  # seconds to suppress LLM retries after connection failure
    llm_connect_timeout_sec: float = 5.0  # timeout in seconds for the startup health-check probe
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 5000


_EXPECTED_KEYS: dict[str, type] = {
    "frequencies_hz": list,
    "dwell_time_sec": (int, float),
    "num_samples": int,
    "lna_gain_db": (int, float),
    "vga_gain_db": (int, float),
    "amp_enable": bool,
    "queue_maxsize": int,
    "host": str,
    "port": int,
}


def load_config(path: str = "config/mimir.yaml") -> MimirConfig:
    if not os.path.isfile(path):
        raise ConfigError(f"Config file not found: {path}")

    with open(path, "r") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must contain a top-level mapping, got {type(raw).__name__}")

    scanner = raw.get("scanner")
    if not isinstance(scanner, dict):
        raise ConfigError("Missing or invalid 'scanner:' section in config")

    dashboard = raw.get("dashboard")
    if not isinstance(dashboard, dict):
        raise ConfigError("Missing or invalid 'dashboard:' section in config")

    scanner_required = {
        "frequencies_hz": list,
        "dwell_time_sec": (int, float),
        "num_samples": int,
        "lna_gain_db": (int, float),
        "vga_gain_db": (int, float),
        "amp_enable": bool,
        "queue_maxsize": int,
        "llm_url": str,
    }

    for key, expected_type in scanner_required.items():
        if key not in scanner:
            raise ConfigError(f"Missing required key 'scanner.{key}'")
        value = scanner[key]
        if not isinstance(value, expected_type):
            raise ConfigError(
                f"Key 'scanner.{key}' has type {type(value).__name__}, "
                f"expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}"
            )

    llm_cooldown_sec = float(scanner.get("llm_cooldown_sec", 60.0))
    llm_connect_timeout_sec = float(scanner.get("llm_connect_timeout_sec", 5.0))

    dashboard_required = {
        "host": str,
        "port": int,
    }

    for key, expected_type in dashboard_required.items():
        if key not in dashboard:
            raise ConfigError(f"Missing required key 'dashboard.{key}'")
        value = dashboard[key]
        if not isinstance(value, expected_type):
            raise ConfigError(
                f"Key 'dashboard.{key}' has type {type(value).__name__}, "
                f"expected {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}"
            )

    freqs = scanner["frequencies_hz"]
    if not freqs:
        raise ConfigError("'scanner.frequencies_hz' must be a non-empty list")

    return MimirConfig(
        frequencies_hz=[float(f) for f in freqs],
        dwell_time_sec=float(scanner["dwell_time_sec"]),
        num_samples=int(scanner["num_samples"]),
        lna_gain_db=float(scanner["lna_gain_db"]),
        vga_gain_db=float(scanner["vga_gain_db"]),
        amp_enable=bool(scanner["amp_enable"]),
        queue_maxsize=int(scanner["queue_maxsize"]),
        llm_url=str(scanner["llm_url"]),
        llm_cooldown_sec=llm_cooldown_sec,
        llm_connect_timeout_sec=llm_connect_timeout_sec,
        dashboard_host=str(dashboard["host"]),
        dashboard_port=int(dashboard["port"]),
    )
