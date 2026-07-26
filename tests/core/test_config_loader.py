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


class TestMimirConfigDefaults:
    """Tests for MimirConfig dataclass defaults."""

    def test_lna_gain_default_is_calibrated(self):
        """MimirConfig.lna_gain_db default must be 24.0 after calibration."""
        cfg = MimirConfig()
        assert cfg.lna_gain_db == 24.0

    def test_vga_gain_default_is_calibrated(self):
        """MimirConfig.vga_gain_db default must be 26.0 after calibration."""
        cfg = MimirConfig()
        assert cfg.vga_gain_db == 26.0

    def test_amp_enable_default_is_false(self):
        """MimirConfig.amp_enable default must remain False for safety."""
        cfg = MimirConfig()
        assert cfg.amp_enable is False

    def test_unchanged_emit_interval_default_is_5(self):
        """MimirConfig.unchanged_emit_interval_sec default must be 5.0."""
        cfg = MimirConfig()
        assert cfg.unchanged_emit_interval_sec == 5.0


def _valid_config() -> dict:
    return copy.deepcopy({
        "scanner": {
            "frequencies_hz": [98000000, 145175000, 915000000, 1090000000],
            "dwell_time_sec": 2.0,
            "num_samples": 2000000,
            "lna_gain_db": 32,
            "vga_gain_db": 40,
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
            assert cfg.lna_gain_db == 32.0
            assert cfg.vga_gain_db == 40.0
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

    def test_loads_unchanged_emit_interval_when_present(self):
        """An explicit unchanged_emit_interval_sec in scanner: is honoured."""
        data = _valid_config()
        data["scanner"]["unchanged_emit_interval_sec"] = 7.5
        path = _write_config(data)
        try:
            cfg = load_config(path)
            assert cfg.unchanged_emit_interval_sec == 7.5
        finally:
            os.unlink(path)

    def test_missing_unchanged_emit_interval_falls_back_to_5(self):
        """The key is optional: a config without it falls back to 5.0."""
        path = _write_config(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.unchanged_emit_interval_sec == 5.0
        finally:
            os.unlink(path)
