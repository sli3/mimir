"""
tests/core/test_config_loader.py
Mimir RF Scanner — Config Loader Tests

Tests for core/config/loader.py
"""

import copy
import os
import sys
import tempfile

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.config.loader import ConfigError, MimirConfig, load_config


def _valid_config() -> dict:
    return copy.deepcopy({
        "scanner": {
            "frequencies_hz": [98000000, 145175000, 915000000, 1090000000],
            "dwell_time_sec": 2.0,
            "num_samples": 2000000,
            "lna_gain_db": 16,
            "vga_gain_db": 20,
            "amp_enable": False,
            "queue_maxsize": 20,
            "llm_url": "http://192.168.0.66:8080/v1",
        },
        "dashboard": {
            "host": "127.0.0.1",
            "port": 5000,
        },
    })


def _write_config(data: dict) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, tmp)
    tmp.close()
    return tmp.name


class TestConfigLoader:
    def test_loads_valid_yaml(self):
        path = _write_config(_valid_config())
        try:
            cfg = load_config(path)
            assert isinstance(cfg, MimirConfig)
            assert cfg.frequencies_hz == [98_000_000, 145_175_000, 915_000_000, 1_090_000_000]
            assert cfg.dwell_time_sec == 2.0
            assert cfg.num_samples == 2_000_000
            assert cfg.lna_gain_db == 16.0
            assert cfg.vga_gain_db == 20.0
            assert cfg.amp_enable is False
            assert cfg.queue_maxsize == 20
            assert cfg.dashboard_host == "127.0.0.1"
            assert cfg.dashboard_port == 5000
        finally:
            os.unlink(path)

    def test_missing_key_raises_config_error(self):
        for section, key in [("scanner", "frequencies_hz"), ("dashboard", "host")]:
            data = _valid_config()
            del data[section][key]
            path = _write_config(data)
            try:
                with pytest.raises(ConfigError, match=key):
                    load_config(path)
            finally:
                os.unlink(path)

    def test_wrong_type_raises_config_error(self):
        data = _valid_config()
        data["scanner"]["dwell_time_sec"] = "not_a_number"
        path = _write_config(data)
        try:
            with pytest.raises(ConfigError, match="dwell_time_sec"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_frequencies_list_parsed_correctly(self):
        path = _write_config(_valid_config())
        try:
            cfg = load_config(path)
            expected = [98_000_000.0, 145_175_000.0, 915_000_000.0, 1_090_000_000.0]
            assert cfg.frequencies_hz == expected
            assert all(isinstance(f, float) for f in cfg.frequencies_hz)
        finally:
            os.unlink(path)
