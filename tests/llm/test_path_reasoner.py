"""
tests/llm/test_path_reasoner.py
Mimir RF Scanner — Phase 53 LLM Trajectory Reasoner Tests

PURPOSE
───────
Tests for llm/path_reasoner.py — the manual LLM reasoning path behind
the /radar Path & Trajectory Prediction panel. Mirrors the house
contracts of the Phase 22 classifier offline tests: never raises,
cooldown on ConnectionError ONLY, fence stripping, fallback results.

Run with:
    python -m pytest tests/llm/test_path_reasoner.py -v
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.path_reasoner import (
    _HIGH_TURN_RATE_DEG_PER_SEC,
    PathReasoner,
    ReasoningResult,
)


def _make_facts(**overrides) -> dict:
    """Build a minimal validated physics-facts dict for testing."""
    facts = {
        "icao": "ABC123",
        "callsign": "QFA1",
        "squawk": None,
        "altitude_ft": 35000.0,
        "track": 270.0,
        "groundspeed": 450.0,
        "vertical_rate": 0.0,
        "bearing_deg": 45.0,
        "range_nm": 10.0,
        "theta_deg_per_sec": 0.5,
        "delta_r_nm_per_sec": -0.1,
        "projected_bearing_deg": 67.5,
        "projected_range_nm": 5.5,
        "trail_length": 3,
    }
    facts.update(overrides)
    return facts


def _make_llm_response(payload) -> MagicMock:
    """Build a mock requests.Response returning the given content.

    ``payload`` may be a dict (serialised to JSON) or a raw string
    (used verbatim, e.g. for the fenced-JSON and malformed cases).
    """
    content = payload if isinstance(payload, str) else json.dumps(payload)
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return mock_response


def _ok_payload(**overrides) -> dict:
    payload = {
        "verdict": "Steady cruise on a stable heading",
        "confidence": "high",
        "notes": "Projection consistent with current vector.",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def reasoner() -> PathReasoner:
    """A PathReasoner pointed at a local test server."""
    return PathReasoner(
        base_url="http://localhost:8080/v1",
        model="test-model",
        temperature=0.1,
    )


def _last_user_prompt(mock_post) -> str:
    """Extract the user-message content from the most recent post call."""
    return mock_post.call_args[1]["json"]["messages"][1]["content"]


def _last_system_prompt(mock_post) -> str:
    """Extract the system-message content from the most recent post call."""
    return mock_post.call_args[1]["json"]["messages"][0]["content"]


class TestSuccessPath:
    """Well-formed LLM responses parse into a populated ReasoningResult."""

    @patch("llm.path_reasoner.requests.post")
    def test_success_parses_all_fields(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        result = reasoner.reason(_make_facts())

        assert result.status == "ok"
        assert result.verdict == "Steady cruise on a stable heading"
        assert result.confidence == "high"
        assert result.notes == "Projection consistent with current vector."
        assert result.cause is None
        assert result.raw_response != ""

    @patch("llm.path_reasoner.requests.post")
    def test_success_uses_45_second_timeout(self, mock_post, reasoner):
        """The interactive path must NOT reuse the classifier's 90 s timeout."""
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts())

        assert mock_post.call_args[1]["timeout"] == 45.0

    @patch("llm.path_reasoner.requests.post")
    def test_success_clears_prior_cooldown(self, mock_post, reasoner):
        """A successful call clears _offline_until."""
        reasoner._offline_until = time.time() - 1  # expired cooldown
        mock_post.return_value = _make_llm_response(_ok_payload())

        result = reasoner.reason(_make_facts())

        assert result.status == "ok"
        assert reasoner._offline_until == 0.0

    @patch("llm.path_reasoner.requests.post")
    def test_fenced_json_is_stripped_and_parsed(self, mock_post, reasoner):
        """```json ... ``` fences are stripped before parsing."""
        fenced = "```json\n" + json.dumps(_ok_payload()) + "\n```"
        mock_post.return_value = _make_llm_response(fenced)

        result = reasoner.reason(_make_facts())

        assert result.status == "ok"
        assert result.verdict == "Steady cruise on a stable heading"
        assert result.confidence == "high"

    @patch("llm.path_reasoner.requests.post")
    def test_unexpected_confidence_is_clamped_to_low(self, mock_post, reasoner):
        """A hallucinated confidence tier becomes "low" with a note appended."""
        mock_post.return_value = _make_llm_response(
            _ok_payload(confidence="absolute")
        )

        result = reasoner.reason(_make_facts())

        assert result.status == "ok"
        assert result.confidence == "low"
        assert "clamped" in result.notes


class TestMalformedResponses:
    """Malformed output yields a fallback result and never raises."""

    @patch("llm.path_reasoner.requests.post")
    def test_malformed_json_returns_fallback(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response("this is not json{")

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.verdict == "unavailable"
        assert result.confidence == "low"
        assert result.cause == "parse"

    @patch("llm.path_reasoner.requests.post")
    def test_unexpected_structure_returns_fallback(self, mock_post, reasoner):
        """A response missing the choices key hits the KeyError path."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"no_choices_here": True}
        mock_post.return_value = mock_response

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "parse"


class TestCooldownAsymmetry:
    """ConnectionError ONLY sets cooldown; Timeout/HTTPError/generic do not."""

    @patch("llm.path_reasoner.requests.post")
    def test_timeout_returns_fallback_without_cooldown(self, mock_post, reasoner):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "timeout"
        # Phase 22 asymmetry: Timeout must NOT set cooldown.
        assert reasoner._offline_until == 0.0

    @patch("llm.path_reasoner.requests.post")
    def test_connection_error_sets_cooldown(self, mock_post, reasoner):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "network"
        assert reasoner._offline_until > time.time()

    @patch("llm.path_reasoner.requests.post")
    def test_http_error_does_not_set_cooldown(self, mock_post, reasoner):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=500)
        )
        mock_post.return_value = mock_response

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "http"
        assert reasoner._offline_until == 0.0

    @patch("llm.path_reasoner.requests.post")
    def test_generic_exception_does_not_set_cooldown(self, mock_post, reasoner):
        mock_post.side_effect = ValueError("something completely unexpected")

        result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "unknown"
        assert reasoner._offline_until == 0.0

    def test_cooldown_fast_fail_skips_network(self, reasoner):
        """A second call inside the cooldown window makes no network call."""
        reasoner._offline_until = time.time() + 9999

        with patch("llm.path_reasoner.requests.post") as mock_post:
            result = reasoner.reason(_make_facts())

        assert result.status == "unavailable"
        assert result.cause == "network"
        assert mock_post.called is False


class TestHardRuleFlags:
    """Squawk and turn-rate flag computation and prompt interpolation."""

    @pytest.mark.parametrize("squawk", ["7500", "7600", "7700"])
    @patch("llm.path_reasoner.requests.post")
    def test_emergency_squawks_flagged(self, mock_post, reasoner, squawk):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(squawk=squawk))

        assert "emergency_squawk_flagged : true" in _last_user_prompt(mock_post)

    @pytest.mark.parametrize("squawk", ["1200", "7701", "7702", "0000"])
    @patch("llm.path_reasoner.requests.post")
    def test_non_emergency_squawks_not_flagged(self, mock_post, reasoner, squawk):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(squawk=squawk))

        assert "emergency_squawk_flagged : false" in _last_user_prompt(mock_post)

    @patch("llm.path_reasoner.requests.post")
    def test_none_squawk_not_flagged_and_omitted(self, mock_post, reasoner):
        """Squawk None: flag false AND no squawk line in the prompt."""
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(squawk=None))

        prompt = _last_user_prompt(mock_post)
        assert "emergency_squawk_flagged : false" in prompt
        assert "Squawk" not in prompt

    @patch("llm.path_reasoner.requests.post")
    def test_turn_rate_above_threshold_flagged(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(theta_deg_per_sec=_HIGH_TURN_RATE_DEG_PER_SEC + 0.1))

        assert "high_turn_rate_flagged   : true" in _last_user_prompt(mock_post)

    @patch("llm.path_reasoner.requests.post")
    def test_turn_rate_below_threshold_not_flagged(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(theta_deg_per_sec=_HIGH_TURN_RATE_DEG_PER_SEC - 0.1))

        assert "high_turn_rate_flagged   : false" in _last_user_prompt(mock_post)

    @patch("llm.path_reasoner.requests.post")
    def test_turn_rate_exactly_at_threshold_not_flagged(self, mock_post, reasoner):
        """Boundary: exactly 3.0 deg/s is a standard-rate turn — NOT flagged
        (the comparison is strictly greater than the cutoff)."""
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(theta_deg_per_sec=_HIGH_TURN_RATE_DEG_PER_SEC))

        assert "high_turn_rate_flagged   : false" in _last_user_prompt(mock_post)

    @patch("llm.path_reasoner.requests.post")
    def test_negative_turn_rate_uses_absolute_value(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(
            _make_facts(theta_deg_per_sec=-(_HIGH_TURN_RATE_DEG_PER_SEC + 0.5))
        )

        assert "high_turn_rate_flagged   : true" in _last_user_prompt(mock_post)


class TestPromptContent:
    """System/user prompt construction contracts."""

    @patch("llm.path_reasoner.requests.post")
    def test_system_prompt_contains_au_legal_context(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts())

        system = _last_system_prompt(mock_post)
        assert "Radiocommunications Act 1992" in system
        assert "receive-only" in system

    @patch("llm.path_reasoner.requests.post")
    def test_callsign_appears_upper_cased_in_user_prompt(self, mock_post, reasoner):
        mock_post.return_value = _make_llm_response(_ok_payload())

        reasoner.reason(_make_facts(callsign="qfa1"))

        assert "QFA1" in _last_user_prompt(mock_post)

    @patch("llm.path_reasoner.requests.post")
    def test_none_per_frame_fields_render_as_unknown(self, mock_post, reasoner):
        """Null per-frame ADS-B fields must not raise and must not fabricate 0."""
        mock_post.return_value = _make_llm_response(_ok_payload())

        result = reasoner.reason(
            _make_facts(altitude_ft=None, groundspeed=None)
        )

        assert result.status == "ok"
        prompt = _last_user_prompt(mock_post)
        assert "Altitude            : unknown" in prompt
        assert "Groundspeed         : unknown" in prompt


class TestConstructor:
    def test_no_args_uses_documented_defaults(self):
        reasoner = PathReasoner()

        assert reasoner._cooldown_sec == 60.0
        assert reasoner._timeout_sec == 45.0
        assert reasoner._connect_timeout_sec == 5.0
        assert reasoner._offline_until == 0.0

    def test_result_is_a_reasoning_result_on_every_path(self, reasoner):
        """The never-raises contract includes returning the right type."""
        with patch(
            "llm.path_reasoner.requests.post",
            side_effect=RuntimeError("boom"),
        ):
            result = reasoner.reason(_make_facts())
        assert isinstance(result, ReasoningResult)
