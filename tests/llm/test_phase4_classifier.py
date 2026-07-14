"""
tests/llm/test_phase4_classifier.py
Mimir RF Scanner — Phase 4 Acceptance Tests

PURPOSE
───────
These tests prove the LLM classification layer works correctly without
requiring the actual LLM server to be running. All LLM HTTP calls are
intercepted and replaced with mock responses.

Why mock the LLM?
─────────────────
The LLM server runs on a local machine on your home network. It may not
be available in every environment (CI, a different machine, server offline).
Tests that require a live server are fragile — they fail for reasons that
have nothing to do with the code being tested.

Instead, we mock `requests.post` to return controlled responses. This lets
us test every code path — including error paths like connection failures and
malformed JSON — reliably and without network access.

Run with:
    python -m pytest tests/llm/test_phase4_classifier.py -v
"""

import json
import sys
import os
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.classifier import ClassificationResult, SignalClassifier


# ── Shared test fixtures ───────────────────────────────────────────────────────

def _make_fingerprint(
    center_freq_hz: float = 98_000_000,
    peak_power_db: float = -23.4,
    snr_db: float = 42.1,
    spectral_flatness: float = 0.021,
    timestamp: str = "2026-05-22T14:33:11",
) -> dict:
    """Build a minimal fingerprint dict for testing."""
    return {
        "center_freq_hz": center_freq_hz,
        "peak_power_db": peak_power_db,
        "snr_db": snr_db,
        "spectral_flatness": spectral_flatness,
        "timestamp": timestamp,
    }


def _make_neighbours(
    labels_and_distances: list,
) -> list:
    """
    Build a neighbours list for testing.

    Args:
        labels_and_distances: List of (label, distance) tuples.

    Example:
        _make_neighbours([("fm_broadcast", 0.031), ("fm_broadcast", 0.089)])
    """
    return [
        {"label": label, "distance": distance}
        for label, distance in labels_and_distances
    ]


def _make_llm_response(payload: dict) -> MagicMock:
    """
    Build a mock requests.Response that returns the given dict as JSON.

    This mimics what the LLM server would return for a successful call.
    The response structure follows the OpenAI chat completions format.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(payload)
                }
            }
        ]
    }
    return mock_response


def _valid_fm_payload() -> dict:
    """A valid LLM JSON payload representing an FM broadcast classification."""
    return {
        "signal_type": "fm_broadcast",
        "confidence": "high",
        "confidence_score": 0.94,
        "novel": False,
        "reasoning": (
            "Centre frequency 98.0 MHz falls within the Australian FM broadcast "
            "band (87.5–108 MHz). Two of three nearest neighbours are fm_broadcast "
            "with distances 0.031 and 0.089 — very strong matches. SNR of 42 dB "
            "indicates a clean, strong signal consistent with a broadcast carrier."
        ),
        "au_legal_status": "legal_rx",
        "frequency_band": "fm_broadcast_band",
    }


# ── Standard test fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def classifier() -> SignalClassifier:
    """A SignalClassifier instance pointed at a local test server."""
    return SignalClassifier(
        base_url="http://localhost:8080/v1",
        model="test-model",
        temperature=0.1,
    )


@pytest.fixture
def fm_fingerprint() -> dict:
    return _make_fingerprint()


@pytest.fixture
def fm_neighbours() -> list:
    return _make_neighbours([
        ("fm_broadcast", 0.031),
        ("fm_broadcast", 0.089),
        ("noise",        0.741),
    ])


# ══════════════════════════════════════════════════════════════════════
# GROUP 1 — ClassificationResult dataclass
# ══════════════════════════════════════════════════════════════════════

class TestClassificationResult:
    """Tests for the ClassificationResult dataclass structure."""

    def test_has_all_required_fields(self):
        """ClassificationResult must have all expected fields."""
        field_names = {f.name for f in fields(ClassificationResult)}
        required = {
            "signal_type",
            "confidence",
            "confidence_score",
            "novel",
            "reasoning",
            "au_legal_status",
            "frequency_band",
            "raw_response",
        }
        assert required.issubset(field_names), (
            f"Missing fields: {required - field_names}"
        )

    def test_can_be_instantiated(self):
        """ClassificationResult can be created with all fields."""
        result = ClassificationResult(
            signal_type="fm_broadcast",
            confidence="high",
            confidence_score=0.94,
            novel=False,
            reasoning="Test reasoning.",
            au_legal_status="legal_rx",
            frequency_band="fm_broadcast_band",
            raw_response="{}",
        )
        assert result.signal_type == "fm_broadcast"
        assert result.confidence_score == 0.94
        assert result.novel is False


# ══════════════════════════════════════════════════════════════════════
# GROUP 2 — Successful classification
# ══════════════════════════════════════════════════════════════════════

class TestSuccessfulClassification:
    """Tests for normal happy-path classification."""

    @patch("llm.classifier.requests.post")
    def test_classify_returns_dataclass(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """classify() always returns a ClassificationResult instance."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert isinstance(result, ClassificationResult), (
            "classify() must return a ClassificationResult, not a raw dict "
            "or any other type."
        )

    @patch("llm.classifier.requests.post")
    def test_fm_broadcast_classification(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """FM fingerprint with FM neighbours classifies as fm_broadcast."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert result.signal_type == "fm_broadcast"
        assert result.confidence == "high"
        assert result.confidence_score > 0.5
        assert result.novel is False
        assert result.au_legal_status == "legal_rx"

    @patch("llm.classifier.requests.post")
    def test_reasoning_is_non_empty_string(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """classify() result must always include a non-empty reasoning string."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0, (
            "reasoning must not be empty — it is how the user understands "
            "why the signal was classified as it was."
        )

    @patch("llm.classifier.requests.post")
    def test_novel_signal_flagged(self, mock_post, classifier):
        """Signal with no close neighbours returns novel=True."""
        novel_payload = {
            "signal_type": "unknown",
            "confidence": "low",
            "confidence_score": 0.15,
            "novel": True,
            "reasoning": "All neighbours have distances above 1.5 — no close match found.",
            "au_legal_status": "verify_before_use",
            "frequency_band": "unknown",
        }
        mock_post.return_value = _make_llm_response(novel_payload)

        fingerprint = _make_fingerprint(center_freq_hz=433_000_000)
        neighbours = _make_neighbours([
            ("fm_broadcast", 1.82),
            ("noise",        1.91),
            ("adsb",         2.10),
        ])

        result = classifier.classify(fingerprint, neighbours)
        assert result.novel is True, (
            "A signal with all neighbours at distance > 1.5 must be flagged "
            "as novel — it does not match anything in the store."
        )

    @patch("llm.classifier.requests.post")
    def test_low_confidence_on_mixed_neighbours(self, mock_post, classifier):
        """Conflicting neighbour labels produce low or medium confidence."""
        mixed_payload = {
            "signal_type": "unknown",
            "confidence": "low",
            "confidence_score": 0.3,
            "novel": False,
            "reasoning": "Neighbours are split between fm_broadcast and adsb — cannot determine type.",
            "au_legal_status": "verify_before_use",
            "frequency_band": "unknown",
        }
        mock_post.return_value = _make_llm_response(mixed_payload)

        fingerprint = _make_fingerprint()
        neighbours = _make_neighbours([
            ("fm_broadcast", 0.41),
            ("adsb",         0.44),
            ("noise",        0.60),
        ])

        result = classifier.classify(fingerprint, neighbours)
        assert result.confidence in ("low", "medium"), (
            "Mixed neighbour labels should produce low or medium confidence, "
            f"not high — got '{result.confidence}'."
        )

    @patch("llm.classifier.requests.post")
    def test_raw_response_stored(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """raw_response must store the original LLM output string."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert isinstance(result.raw_response, str)
        assert len(result.raw_response) > 0

    @patch("llm.classifier.requests.post")
    def test_strips_markdown_fences_from_response(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """
        classify() handles LLM responses wrapped in markdown fences.

        Some models return ```json ... ``` even when told not to.
        The parser must strip these before parsing.
        """
        raw_with_fences = "```json\n" + json.dumps(_valid_fm_payload()) + "\n```"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": raw_with_fences}}]
        }
        mock_post.return_value = mock_response

        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert result.signal_type == "fm_broadcast", (
            "classify() must handle markdown-fenced JSON responses from the LLM."
        )


# ══════════════════════════════════════════════════════════════════════
# GROUP 3 — Fallback behaviour
# ══════════════════════════════════════════════════════════════════════

class TestFallbackBehaviour:
    """
    Tests for graceful degradation when the LLM is unreachable
    or returns unusable output.
    """

    @patch("llm.classifier.requests.post")
    def test_llm_connection_error_returns_offline(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """Connection error returns offline result — does not raise."""
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        result = classifier.classify(fm_fingerprint, fm_neighbours)

        assert isinstance(result, ClassificationResult), (
            "classify() must return a ClassificationResult even when the "
            "LLM server is unreachable — not raise an exception."
        )
        assert result.signal_type == "llm_offline"
        assert result.confidence == "low"
        assert result.confidence_score == 0.0

    @patch("llm.classifier.requests.post")
    def test_llm_timeout_returns_fallback(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """Timeout returns fallback result — does not raise."""
        mock_post.side_effect = requests.exceptions.Timeout("timed out")
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert result.signal_type == "unavailable"
        assert "timed out" in result.reasoning.lower() or "unavailable" in result.reasoning.lower()

    @patch("llm.classifier.requests.post")
    def test_json_parse_error_returns_fallback(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """Malformed JSON from LLM returns fallback — does not raise."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "this is not json at all {"}}]
        }
        mock_post.return_value = mock_response

        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert result.signal_type == "unavailable", (
            "Malformed LLM JSON must return a fallback result, not crash."
        )

    @patch("llm.classifier.requests.post")
    def test_fallback_reasoning_is_non_empty(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """Offline result always includes a non-empty reasoning string."""
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert len(result.reasoning) > 0, (
            "Offline result must include a reasoning string explaining "
            "why classification was not possible."
        )

    @patch("llm.classifier.requests.post")
    def test_fallback_au_legal_status_is_verify(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """Offline result sets au_legal_status to verify_before_use."""
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        result = classifier.classify(fm_fingerprint, fm_neighbours)
        assert result.au_legal_status == "verify_before_use"


# ══════════════════════════════════════════════════════════════════════
# GROUP 4 — Prompt content
# ══════════════════════════════════════════════════════════════════════

class TestPromptContent:
    """Tests that the user prompt contains the expected content."""

    def test_prompt_contains_centre_frequency(self, classifier, fm_fingerprint, fm_neighbours):
        """User prompt must include the centre frequency."""
        prompt = classifier._build_user_prompt(fm_fingerprint, fm_neighbours)
        assert "98,000,000" in prompt or "98.000" in prompt or "98" in prompt, (
            "User prompt must include the centre frequency so the LLM can "
            "apply frequency band knowledge."
        )

    def test_prompt_contains_neighbour_distances(self, classifier, fm_fingerprint, fm_neighbours):
        """User prompt must include ChromaDB distance values."""
        prompt = classifier._build_user_prompt(fm_fingerprint, fm_neighbours)
        assert "0.031" in prompt or "0.089" in prompt, (
            "User prompt must include neighbour distance values so the LLM "
            "can weigh the similarity of each match."
        )

    def test_prompt_contains_neighbour_labels(self, classifier, fm_fingerprint, fm_neighbours):
        """User prompt must include neighbour labels."""
        prompt = classifier._build_user_prompt(fm_fingerprint, fm_neighbours)
        assert "fm_broadcast" in prompt, (
            "User prompt must include neighbour labels so the LLM can "
            "see what signal types are in the store."
        )

    def test_prompt_contains_snr(self, classifier, fm_fingerprint, fm_neighbours):
        """User prompt must include SNR value."""
        prompt = classifier._build_user_prompt(fm_fingerprint, fm_neighbours)
        assert "42" in prompt, (
            "User prompt must include the SNR so the LLM can assess signal quality."
        )

    def test_system_prompt_contains_au_frequencies(self, classifier):
        """System prompt must include Australian frequency band reference."""
        system_prompt = classifier._build_system_prompt()
        assert "145.175" in system_prompt, (
            "System prompt must include the AU APRS frequency (145.175 MHz) "
            "so the LLM applies Australian law, not US/EU defaults."
        )
        assert "915" in system_prompt, (
            "System prompt must include the AU ISM/LoRa frequency (915 MHz), "
            "not the EU band (868 MHz)."
        )
        assert "868" not in system_prompt, (
            "System prompt must NOT include 868 MHz — that is the EU LoRa band. "
            "This is an Australian scanner."
        )


# ══════════════════════════════════════════════════════════════════════
# GROUP 5 — API call correctness
# ══════════════════════════════════════════════════════════════════════

class TestApiCallCorrectness:
    """Tests that the API call is made with the correct parameters."""

    @patch("llm.classifier.requests.post")
    def test_temperature_is_low(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """
        API call must use a low temperature (≤ 0.2) for classification.

        High temperature produces unpredictable results. For a classifier
        you want the same input to produce the same output every time.
        """
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        classifier.classify(fm_fingerprint, fm_neighbours)

        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
        assert body["temperature"] <= 0.2, (
            f"Temperature must be ≤ 0.2 for classification — got {body['temperature']}. "
            "High temperature produces inconsistent results."
        )

    @patch("llm.classifier.requests.post")
    def test_system_and_user_messages_sent(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """API call must include both system and user messages."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        classifier.classify(fm_fingerprint, fm_neighbours)

        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
        roles = [m["role"] for m in body["messages"]]
        assert "system" in roles, "API call must include a system message."
        assert "user" in roles, "API call must include a user message."


# ══════════════════════════════════════════════════════════════════════
# GROUP 6 — TX and AU legal safety
# ══════════════════════════════════════════════════════════════════════

class TestSafetyChecks:
    """TX safety and AU legal compliance checks."""

    def test_no_tx_patterns_in_classifier(self):
        """
        classifier.py must contain no transmit-related patterns.

        This is a static code check — reads the file directly and greps
        for known TX function names. Any match is a blocker.
        """
        import pathlib

        classifier_path = pathlib.Path(__file__).parent.parent.parent / "llm" / "classifier.py"
        assert classifier_path.exists(), (
            f"classifier.py not found at expected path: {classifier_path}"
        )

        source = classifier_path.read_text()

        forbidden = [
            "writeStream",
            "SOAPY_SDR_TX",
            "hackrf_start_tx",
            "set_tx_gain",
            "set_tx_frequency",
            "setupTxStream",
            "activateTxStream",
        ]

        for pattern in forbidden:
            assert pattern not in source, (
                f"TX pattern '{pattern}' found in classifier.py — "
                f"this is a TX safety violation. Remove it immediately."
            )

    def test_system_prompt_does_not_contain_eu_frequencies(self, classifier):
        """System prompt must not reference EU frequencies (868 MHz)."""
        system_prompt = classifier._build_system_prompt()
        assert "868" not in system_prompt, (
            "System prompt must not contain 868 MHz — that is the EU LoRa band. "
            "Australian LoRa operates at 915 MHz."
        )

    def test_system_prompt_does_not_contain_us_aprs(self, classifier):
        """System prompt must not reference the US APRS frequency (144.390 MHz)."""
        system_prompt = classifier._build_system_prompt()
        assert "144.390" not in system_prompt and "144390" not in system_prompt, (
            "System prompt must not contain 144.390 MHz — that is the US APRS "
            "frequency. Australian APRS is 145.175 MHz."
        )


# ══════════════════════════════════════════════════════════════════════
# GROUP 7 — ACMA allocations in prompt
# ══════════════════════════════════════════════════════════════════════

class TestAcmaAllocationsInPrompt:
    """Tests for ACMA spectrum plan context in the user prompt."""

    _ACMA_FM_ALLOCATION = [
        {
            "freq_start_mhz": 87.5,
            "freq_end_mhz": 108.0,
            "services": ["BROADCASTING", "Fixed", "Mobile"],
            "mimir_band": "fm_broadcast",
        },
    ]

    def test_acma_section_appears_when_provided(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """ACMA section appears when acma_allocations list is non-empty."""
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=self._ACMA_FM_ALLOCATION,
        )
        assert "ACMA" in prompt, (
            "User prompt must include an ACMA section when allocations "
            "are provided."
        )

    def test_acma_contains_frequency_range(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """ACMA section includes the allocation frequency range."""
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=self._ACMA_FM_ALLOCATION,
        )
        assert "87.5" in prompt and "108.0" in prompt, (
            "ACMA section must include the frequency range from the "
            "allocation entry."
        )

    def test_acma_contains_service_name(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """ACMA section includes the service name (e.g. BROADCASTING)."""
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=self._ACMA_FM_ALLOCATION,
        )
        assert "BROADCASTING" in prompt, (
            "ACMA section must include the primary service name from "
            "the allocation entry."
        )

    def test_empty_allocations_no_acma_section(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """Empty allocations list omits the ACMA spectrum plan section."""
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=[],
        )
        assert "ACMA SPECTRUM PLAN" not in prompt, (
            "User prompt must not include the ACMA spectrum plan section "
            "when the allocations list is empty."
        )
        assert "ACMA allocation" in prompt, (
            "User prompt must still demote ACMA in the evidence-priority text."
        )

    def test_none_allocations_no_acma_section(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """None allocations omits the ACMA spectrum plan section (backwards compat)."""
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=None,
        )
        assert "ACMA SPECTRUM PLAN" not in prompt, (
            "User prompt must not include the ACMA spectrum plan section when "
            "acma_allocations is None."
        )
        assert "ACMA allocation" in prompt, (
            "User prompt must still demote ACMA in the evidence-priority text."
        )

    @patch("llm.classifier.requests.post")
    def test_classify_passes_allocations_through(
        self, mock_post, classifier, fm_fingerprint, fm_neighbours
    ):
        """classify() with acma_allocations does not crash and calls the API."""
        mock_post.return_value = _make_llm_response(_valid_fm_payload())
        result = classifier.classify(
            fm_fingerprint, fm_neighbours,
            acma_allocations=self._ACMA_FM_ALLOCATION,
        )
        assert isinstance(result, ClassificationResult)
        assert result.signal_type == "fm_broadcast"

    def test_acma_notes_appear_when_non_empty(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """ACMA section includes the notes field when it is non-empty."""
        allocation_with_notes = [
            {
                "freq_start_mhz": 12.2,
                "freq_end_mhz": 12.5,
                "services": ["BROADCASTING"],
                "mimir_band": "satellite_tv",
                "notes": "Ku band satellite TV — mixed BSS/FSS.",
            },
        ]
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=allocation_with_notes,
        )
        assert "Notes:" in prompt, (
            "User prompt must include a 'Notes:' line when the ACMA "
            "allocation has a non-empty notes field."
        )
        assert "Ku band satellite TV" in prompt, (
            "User prompt must contain the actual notes text from the "
            "allocation entry."
        )

    def test_acma_notes_omitted_when_empty(
        self, classifier, fm_fingerprint, fm_neighbours
    ):
        """ACMA section does not include a Notes line when notes is empty."""
        allocation_without_notes = [
            {
                "freq_start_mhz": 87.5,
                "freq_end_mhz": 108.0,
                "services": ["BROADCASTING"],
                "mimir_band": "fm_broadcast",
                "notes": "",
            },
        ]
        prompt = classifier._build_user_prompt(
            fm_fingerprint, fm_neighbours,
            acma_allocations=allocation_without_notes,
        )
        assert "Notes:" not in prompt, (
            "User prompt must not include a 'Notes:' line when the "
            "allocation notes field is empty."
        )


# ══════════════════════════════════════════════════════════════════════
# GROUP 8 — AU band reference completeness
# ══════════════════════════════════════════════════════════════════════

class TestBandReferenceCompleteness:
    """Tests that all mimir_band labels from the ACMA file are in the system prompt."""

    _ALL_MIMIR_BANDS = [
        "fm_broadcast", "am_broadcast", "dab_plus",
        "aviation_vhf", "acars", "aeronautical_comms", "ils_vor",
        "adsb", "gnss", "aprs", "amateur",
        "ism_lora", "uhf_cb", "pmr_land_mobile",
        "uhf_tv", "mobile_cellular",
        "marine_vhf", "ais", "marine_hf", "marine_satellite",
        "epirb_plb", "noaa_weather_sat", "met_satellite",
        "satellite_tv", "time_signal",
    ]

    def test_all_mimir_bands_in_system_prompt(self, classifier):
        """Every mimir_band label must appear in the AU band reference."""
        system_prompt = classifier._build_system_prompt()
        missing = []
        for band in self._ALL_MIMIR_BANDS:
            if band not in system_prompt:
                missing.append(band)
        assert not missing, (
            f"System prompt is missing the following mimir_band labels: "
            f"{missing}. The _AU_BAND_REFERENCE must be updated whenever "
            f"new labels are added to frequency_reference.json."
        )

    def test_no_fcc_etsi_in_system_prompt(self, classifier):
        """System prompt must not contain FCC or ETSI references."""
        system_prompt = classifier._build_system_prompt()
        assert "FCC" not in system_prompt, (
            "System prompt must not reference FCC — AU jurisdiction only."
        )
        assert "ETSI" not in system_prompt, (
            "System prompt must not reference ETSI — AU jurisdiction only."
        )
