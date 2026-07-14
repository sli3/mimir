"""
llm/classifier.py — LLM Signal Classification Layer

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
───────────────────
This is the reasoning layer at the end of the Mimir pipeline.

By the time we get here, Phase 2 has produced a fingerprint (a compact
numerical description of the signal) and Phase 3 has queried ChromaDB
for the most similar signals it has seen before.

This module takes both of those and asks a local LLM:
  "Given this fingerprint and these similar past signals — what is this?"

The LLM returns a structured JSON classification: signal type, confidence,
reasoning in plain English, and a flag for signals it has never seen before.

WHY A LOCAL LLM?
────────────────
The vector store (ChromaDB) is very good at finding similar signals, but
it cannot interpret ambiguous results, apply frequency band knowledge, or
explain its reasoning. The LLM can do all three.

Example: if the three nearest neighbours are two FM matches (distance 0.03)
and one noise match (distance 0.74), a simple majority vote would say FM —
but the LLM can also note that 98 MHz is squarely in the FM broadcast band,
that the SNR is 42 dB (strong, clean), and that the noise match is distant
enough to be irrelevant. That reasoning is what makes the classification
trustworthy rather than just a number.
"""

import json
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── Deterministic confidence-cap thresholds ───────────────────────────────────
# HEURISTIC and tunable — NOT field-calibrated. These are a deterministic
# backstop applied AFTER the LLM returns (see _apply_confidence_caps). They exist
# because confidence_score is set entirely by the LLM — there is no upstream
# formula — so a frequency + ACMA match can talk the model into "high" even when
# the live signal is weak or noise-shaped. These thresholds target that observed
# false-positive shape while staying conservative enough not to suppress a
# genuine weak-but-real signal. Revisit once live-aircraft captures give a real
# picture of what a true weak signal's margin/bandwidth looks like on this
# hardware (tracked alongside the ADS-B field-verification work).
_MARGIN_FLOOR_DB: float = 6.0          # min SNR-above-threshold for full confidence
_NEAR_ZERO_BINS: int = 1               # <= this many occupied bins = spike/noise
_NOISE_FLATNESS: float = 0.9           # spectral flatness >= this = near-white noise
_CAPPED_CONFIDENCE_SCORE: float = 0.4  # ceiling applied when any cap triggers


@dataclass
class ClassificationResult:
    """
    The output of a single LLM classification call.

    Fields
    ──────
    signal_type      : Best guess at what the signal is.
                        Examples: "fm_broadcast", "am_broadcast", "dab_plus",
                        "aviation_vhf", "acars", "aeronautical_comms", "ils_vor",
                        "adsb", "gnss", "aprs", "amateur", "ism_lora", "uhf_cb",
                        "pmr_land_mobile", "uhf_tv", "mobile_cellular",
                        "marine_vhf", "ais", "marine_hf", "marine_satellite",
                        "epirb_plb", "noaa_weather_sat", "met_satellite",
                        "satellite_tv", "time_signal", "noise", "unknown".
                        "unavailable" means classification failed for a
                        non-network reason (malformed JSON, unexpected response
                        structure, etc.).
                        "llm_offline" means the LLM server is unreachable
                        (ConnectionError, or cooldown active after a recent
                        connection failure).

    confidence       : Human-readable confidence tier.
                       "high"   = LLM is confident in the classification.
                       "medium" = some uncertainty, e.g. mixed neighbours.
                       "low"    = very uncertain — treat result cautiously.

    confidence_score : Machine-readable confidence as 0.0–1.0.
                       Useful for filtering or thresholding downstream.

    novel            : True = this signal does not closely match anything
                       in the ChromaDB store. Treat with extra caution —
                       it may be a signal type Mimir has not seen before.

    reasoning        : Plain English explanation of why the LLM classified
                       the signal this way. Useful for debugging and for
                       building trust in the system.

    au_legal_status  : "legal_rx"         = frequency is in a known AU
                                            legal passive-receive band.
                       "verify_before_use" = frequency is outside known
                                            bands or LLM could not verify.

    frequency_band   : Which AU band the signal appears to be in.
                        Examples: "fm_broadcast_band", "am_broadcast_band",
                        "dab_plus_band", "aviation_vhf_band", "acars_band",
                        "aeronautical_comms_band", "ils_vor_band", "adsb_band",
                        "gnss_band", "aprs_band", "amateur_band",
                        "ism_lora_band", "uhf_cb_band", "pmr_land_mobile_band",
                        "uhf_tv_band", "mobile_cellular_band",
                        "marine_vhf_band", "ais_band", "marine_hf_band",
                        "marine_satellite_band", "epirb_plb_band",
                        "noaa_weather_sat_band", "met_satellite_band",
                        "satellite_tv_band", "time_signal_band", "unknown".

    raw_response     : The raw string the LLM returned. Kept for debugging
                       — useful if the JSON parse fails or the result looks
                       wrong and you want to see exactly what the LLM said.
    """
    signal_type: str
    confidence: str
    confidence_score: float
    novel: bool
    reasoning: str
    au_legal_status: str
    frequency_band: str
    raw_response: str


# ── Australian frequency band reference ───────────────────────────────────────
# Used in the system prompt. Defined here as a constant so it stays in sync
# with the rest of the codebase rather than being buried in a string.

_AU_BAND_REFERENCE = """
Australian frequency bands (legal to receive passively — no licence required):
  FM Broadcast       : 87.5 MHz – 108 MHz
  AM Broadcast       : 526.5 kHz – 1606.5 kHz (medium-wave radio)
  DAB+ Digital Radio : 174 MHz – 230 MHz
  Aviation VHF       : 118 MHz – 136 MHz (ATC and aircraft comms)
  ACARS              : 129.0 MHz – 130.1 MHz (aircraft digital messaging — 129.125 MHz primary)
  Aeronautical Comms : 4.2 GHz – 5.091 GHz (C-band airborne data links, radio altimeters)
  ILS / VOR          : 74.8 MHz – 335.4 MHz (instrument landing and navigation aids)
  ADS-B              : 1090 MHz (aircraft GPS position, mandatory unencrypted broadcast)
  GNSS               : 1164 MHz – 1610 MHz (GPS, GLONASS, Galileo, BeiDou downlinks)
  APRS               : 145.175 MHz (Australian APRS frequency)
  Amateur            : 47 MHz – 5850 MHz (multiple hobby radio bands across the spectrum)
  ISM / LoRa         : 915 MHz (Australian/NZ ISM band)
  UHF CB             : 476.425 MHz – 477.400 MHz (citizens band, 80 channels, within 470–520 MHz allocation)
  PMR Land Mobile    : 403 MHz – 470 MHz (professional handheld / emergency services)
  UHF TV             : 520 MHz – 694 MHz (digital terrestrial television)
  Mobile Cellular    : 694 MHz – 2690 MHz (4G/5G mobile phone towers)
  Marine VHF         : 156.5 MHz – 162.0 MHz (ship and coast radio)
  AIS                : 161.9 MHz – 162.1 MHz (maritime vessel tracking — 161.975/162.025 MHz)
  Marine HF          : 4 MHz – 27.5 MHz (long-range maritime HF comms, ITU marine bands)
  Marine Satellite   : 1621.35 MHz – 1626.5 MHz (Inmarsat, Iridium satphone downlinks)
  EPIRB / PLB        : 406 MHz – 406.1 MHz (distress beacons, emergency only)
  NOAA Weather Sat   : 137 MHz – 138 MHz (NOAA 15: 137.620 MHz, NOAA 18: 137.9125 MHz, NOAA 19: 137.100 MHz, Meteor-M2: 137.9 MHz — all passive downlinks)
  Met Satellite      : 400.15 MHz – 1710 MHz (weather satellite imagery downlinks, NOAA/Meteosat)
  Satellite TV       : 11.7 GHz – 12.75 GHz (Ku-band Foxtel/Optus downlinks, household dish)
  Time Signal        : 20 kHz, 400.1 MHz, 2.5 GHz, 5 GHz (precision time/frequency reference broadcasts)
""".strip()

# ── ChromaDB distance scale reference ─────────────────────────────────────────
# Explains to the LLM what the distance numbers mean.
#
# NOTE: These thresholds were calibrated against 6-dimensional L2-normalised
# embeddings (peak_freq_hz, peak_power_db, noise_floor_db, snr_db, bandwidth_hz,
# occupied_bins). Phase 13 expanded the vector to 7D (added spectral_flatness).
# After a ChromaDB re-seed with 7D vectors, these thresholds WILL shift — L2
# distances scale with sqrt(dimension), so 7D distances will be slightly larger
# than 6D for the same signal pair. Recalibrate via tools/calibrate_thresholds.py
# once live captures are available with the telescopic whip antenna. Tracked under
# 9C-Threshold (open).

_DISTANCE_SCALE_REFERENCE = """
ChromaDB distance scale (lower = more similar):
Calibrated from real HackRF One captures — Adelaide, AU — June 2026.

  0.000 – 0.004 : Strong match   — almost certainly the same signal type
  0.004 – 0.031 : Possible match — likely same type, moderate confidence
  0.031 – 0.052 : Different type — known signal but different category
  0.052+        : Novel signal   — does not closely match anything stored

Reference distances from calibration:
  FM broadcast same-type:    0.0019  (very stable)
  Aviation VHF same-type:    0.0000  (near-identical captures)
  APRS same-type:            0.0009  (very stable)
  Aviation VHF vs APRS:      0.0575  (closest cross-type pair)
  FM vs noise:               1.3500  (FM is highly distinctive)

Note: ACARS, AIS, and Aviation VHF share identical gain settings (lna=16/vga=20).
Without live signal, their noise captures are nearly indistinguishable in vector
space. The LLM should rely on centre frequency as the primary discriminator for
those bands.
""".strip()

# ── Required JSON output schema ────────────────────────────────────────────────
# Shown verbatim in the system prompt so the LLM knows exactly what to return.

_JSON_SCHEMA = """
{
  "signal_type":       string,   // e.g. "fm_broadcast", "am_broadcast", "dab_plus", "aviation_vhf", "acars", "aeronautical_comms", "ils_vor", "adsb", "gnss", "aprs", "amateur", "ism_lora", "uhf_cb", "pmr_land_mobile", "uhf_tv", "mobile_cellular", "marine_vhf", "ais", "marine_hf", "marine_satellite", "epirb_plb", "noaa_weather_sat", "met_satellite", "satellite_tv", "time_signal", "noise", "unknown"
  "confidence":        string,   // "high", "medium", or "low"
  "confidence_score":  float,    // 0.0 to 1.0
  "novel":             boolean,  // true if no close ChromaDB match exists
  "reasoning":         string,   // plain English explanation of the classification
  "au_legal_status":   string,   // "legal_rx" or "verify_before_use"
  "frequency_band":    string    // "fm_broadcast_band", "am_broadcast_band", "dab_plus_band", "aviation_vhf_band", "acars_band", "aeronautical_comms_band", "ils_vor_band", "adsb_band", "gnss_band", "aprs_band", "amateur_band", "ism_lora_band", "uhf_cb_band", "pmr_land_mobile_band", "uhf_tv_band", "mobile_cellular_band", "marine_vhf_band", "ais_band", "marine_hf_band", "marine_satellite_band", "epirb_plb_band", "noaa_weather_sat_band", "met_satellite_band", "satellite_tv_band", "time_signal_band", or "unknown"
}
""".strip()


class SignalClassifier:
    """
    LLM-based signal classifier for the Mimir RF scanner.

    Takes a Phase 2 fingerprint and Phase 3 ChromaDB neighbours,
    constructs a structured prompt, calls the local LLM, and returns
    a ClassificationResult.

    Usage:
        classifier = SignalClassifier(
            base_url="http://192.168.0.66:8080/v1",
            model="Qwen3-4B-Mimir",
        )
        result = classifier.classify(fingerprint, neighbours)
        print(result.signal_type)    # e.g. "fm_broadcast"
        print(result.reasoning)      # plain English explanation

    If the LLM server is unreachable or returns malformed output,
    classify() returns a fallback ClassificationResult rather than
    raising an exception — so the pipeline continues gracefully.
    """

    _FALLBACK_SIGNAL_TYPE = "unavailable"
    _OFFLINE_SIGNAL_TYPE = "llm_offline"
    _REQUEST_TIMEOUT_SEC = 90

    def __init__(
        self,
        base_url: str = "http://192.168.0.66:8080/v1",
        model: str = "Qwen3-4B-Mimir",
        temperature: float = 0.1,
        cooldown_sec: float = 60.0,
        connect_timeout_sec: float = 5.0,
    ) -> None:
        """
        Initialise the classifier.

        Args:
            base_url    : Base URL of the local LLM server (OpenAI-compatible).
                          Default: Qwen3-4B-Mimir via llama.cpp on yubaba.
            model       : Model name to pass to the API.
            temperature : LLM temperature. Keep low (0.1) for classification —
                          you want consistent, deterministic results, not creativity.
            cooldown_sec: Seconds to suppress LLM retries after a connection failure.
            connect_timeout_sec: Timeout in seconds for the startup health-check probe.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._cooldown_sec = cooldown_sec
        self._connect_timeout_sec = connect_timeout_sec
        self._offline_until: float = 0.0

    # ── Public interface ───────────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """Probe the LLM server at startup and set cooldown if unreachable.

        Never raises. Returns True if the server is reachable, False otherwise.
        An HTTP error (e.g. 404 from /models) is treated as reachable because
        not every build exposes that endpoint.

        This is called by scan.py at startup to pre-warm the connection state.
        If the server is unreachable, the classifier enters a cooldown period
        and will return offline results for any classification requests until
        the cooldown expires.
        """
        try:
            response = requests.get(
                f"{self._base_url}/models",
                timeout=self._connect_timeout_sec,
            )
            response.raise_for_status()
            self._offline_until = 0.0
            logger.info("LLM server reachable at %s", self._base_url)
            return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            self._offline_until = time.time() + self._cooldown_sec
            logger.warning(
                "LLM server unreachable at %s — cooldown active for %.0f s",
                self._base_url,
                self._cooldown_sec,
            )
            return False
        except requests.exceptions.HTTPError:
            self._offline_until = 0.0
            logger.info(
                "LLM server reachable at %s (/models returned HTTP error — may be OK)",
                self._base_url,
            )
            return True

    def classify(
        self,
        fingerprint: dict,
        neighbours: list,
        acma_allocations: list[dict] | None = None,
    ) -> ClassificationResult:
        """
        Classify a signal using the local LLM.

        Args:
            fingerprint : Signal fingerprint dict from Phase 2
                          fingerprint_spectrum(). Must contain at minimum:
                          center_freq_hz, peak_power_db, snr_db,
                          spectral_flatness, timestamp. Also uses, when present:
                          bandwidth_hz, occupied_bins, snr_margin_db,
                          peak_bin_power_db — fed to the prompt as measured
                          evidence and used by _apply_confidence_caps(). Missing
                          optional fields degrade gracefully (labelled "unknown",
                          and the corresponding cap simply does not fire).

            neighbours  : List of neighbour dicts from Phase 3
                          SignalStore.query(). Each dict must contain
                          at minimum: label, distance.

            acma_allocations: Optional list of ACMA spectrum plan dicts
                          covering this frequency. Each dict should contain
                          freq_start_mhz, freq_end_mhz, services, mimir_band,
                          and optionally notes. Passed through to the user
                          prompt so the LLM can use regulatory context when
                          classifying. None or empty list to omit.

        Returns:
            ClassificationResult — always. Never raises on LLM failure.
            On server error or malformed response, returns a fallback
            result with signal_type="unavailable" and confidence="low".
        """
        # Fast-fail during cooldown — no network call if server known-offline
        if time.time() < self._offline_until:
            return self._offline_result()

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            fingerprint, neighbours, acma_allocations=acma_allocations
        )

        try:
            logger.info(
                "Classifying signal at %.3f MHz via LLM...",
                fingerprint.get("center_freq_hz", 0) / 1e6,
            )

            response = requests.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "temperature": self._temperature,
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                },
                timeout=self._REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()

            raw = response.json()["choices"][0]["message"]["content"]
            self._offline_until = 0.0  # Server is back — clear cooldown
            logger.debug("LLM raw response: %s", raw)
            result = self._parse_response(raw)
            return self._apply_confidence_caps(result, fingerprint)

        except requests.exceptions.ConnectionError:
            self._offline_until = time.time() + self._cooldown_sec
            logger.warning(
                "LLM server unreachable at %s — cooldown active for %.0f s",
                self._base_url,
                self._cooldown_sec,
            )
            return self._offline_result()
        except requests.exceptions.Timeout:
            logger.warning(
                "LLM server timed out after %s seconds", self._REQUEST_TIMEOUT_SEC
            )
            # NOTE: Timeout does NOT trigger cooldown — only ConnectionError does.
            # This asymmetry means a timeout will return "unavailable" but not block
            # subsequent requests for the cooldown period. This is intentional per
            # Phase 22 spec: only ConnectionError sets cooldown; Timeout is treated
            # as a transient error without blocking future requests.
            return self._fallback_result(
                f"LLM server unreachable — request timed out after "
                f"{self._REQUEST_TIMEOUT_SEC} seconds."
            )
        except requests.exceptions.HTTPError as err:
            logger.warning("LLM server returned HTTP error: %s", err)
            return self._fallback_result(f"LLM server error — {err}")
        except (KeyError, IndexError) as err:
            logger.warning("Unexpected LLM response structure: %s", err)
            return self._fallback_result(
                f"Unexpected LLM response structure — {err}"
            )
        except Exception as err:
            logger.warning("LLM classification failed unexpectedly: %s", err)
            return self._fallback_result(f"Classification unavailable — {err}")

    def _offline_result(self) -> ClassificationResult:
        """Return a ClassificationResult indicating the LLM server is offline.

        Used when the LLM server is unreachable (ConnectionError) or when the
        classifier is in cooldown after a recent connection failure. This
        provides a graceful fallback that allows the pipeline to continue
        operating without crashing.

        The result includes a human-readable reasoning message that explains
        the offline status and suggests checking the LLM server status.
        """
        return ClassificationResult(
            signal_type=self._OFFLINE_SIGNAL_TYPE,
            confidence="low",
            confidence_score=0.0,
            novel=False,
            reasoning=(
                f"LLM server offline at {self._base_url}. "
                f"Cooldown active — next retry in "
                f"{max(0.0, self._offline_until - time.time()):.0f} s. "
                f"Check yubaba is running and Mimir is on the home network."
            ),
            au_legal_status="verify_before_use",
            frequency_band="unknown",
            raw_response="",
        )

    # ── Deterministic confidence caps ──────────────────────────────────────────

    def _apply_confidence_caps(
        self, result: ClassificationResult, fingerprint: dict
    ) -> ClassificationResult:
        """Clamp confidence when the measured signal looks weak or noise-like.

        The LLM sets confidence_score itself — there is no upstream formula — so
        a frequency + ACMA match can push it to "high" even for a signal that is
        barely above the noise floor or occupies no real bandwidth. This method
        is a deterministic backstop the prompt wording cannot be reasoned past.

        SAFETY: this runs on the FINGERPRINT classification path only. Confirmed
        ADS-B decodes are emitted by emit_adsb_scan_result() as ground truth
        (source="decode") and never call classify(), so these caps cannot dim a
        real decoded aircraft. Confirm that caller separation holds before relying
        on this property.

        When any cap triggers, confidence_score is clamped to
        _CAPPED_CONFIDENCE_SCORE, the tier is set to "low", and a note is appended
        to reasoning explaining why. signal_type is left untouched — this gates
        confidence, it does not re-classify.
        """
        snr_margin_db = fingerprint.get("snr_margin_db")
        occupied_bins = fingerprint.get("occupied_bins")
        flatness = fingerprint.get("spectral_flatness")

        reasons: list[str] = []

        # Cap 1 — marginal SNR. snr_margin_db is SNR above the per-band calibrated
        # detection threshold. A small margin means the signal is barely clearing
        # the noise floor, whatever its absolute SNR.
        if snr_margin_db is not None and snr_margin_db < _MARGIN_FLOOR_DB:
            reasons.append(
                f"SNR margin {snr_margin_db:.1f} dB below the "
                f"{_MARGIN_FLOOR_DB:.0f} dB confidence floor "
                f"(barely above detection threshold)"
            )

        # Cap 2 — no real occupied bandwidth AND noise-shaped. A signal occupying
        # at most one FFT bin AND with near-white spectral flatness is a
        # spike/noise, not a modulated signal. The flatness condition deliberately
        # protects genuine narrow tonal signals (low flatness), which are NOT
        # capped by this rule.
        if (
            occupied_bins is not None
            and flatness is not None
            and occupied_bins <= _NEAR_ZERO_BINS
            and flatness >= _NOISE_FLATNESS
        ):
            reasons.append(
                f"occupies {occupied_bins} bin(s) with spectral flatness "
                f"{flatness:.3f} (near-white) — no real occupied bandwidth"
            )

        if not reasons:
            return result

        capped_score = min(result.confidence_score, _CAPPED_CONFIDENCE_SCORE)
        note = (
            " [confidence capped by signal-quality gate: "
            + "; ".join(reasons)
            + "]"
        )
        logger.info(
            "Confidence capped %.2f -> %.2f at %.3f MHz: %s",
            result.confidence_score,
            capped_score,
            fingerprint.get("center_freq_hz", 0) / 1e6,
            "; ".join(reasons),
        )
        return replace(
            result,
            confidence_score=capped_score,
            confidence="low",
            reasoning=result.reasoning + note,
        )

    # ── Prompt construction ────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt — fixed instructions sent with every call.

        This tells the LLM its role, the AU frequency band reference,
        the ChromaDB distance scale, and the exact JSON format to return.
        """
        return f"""You are a passive RF signal classifier for Mimir, an AI-powered \
radio spectrum scanner operating in Adelaide, South Australia, Australia.

LEGAL CONTEXT
You operate under Australian law (Radiocommunications Act 1992, Cth).
This system is receive-only. It never transmits. All signals analysed are \
publicly broadcast signals that are legal to receive passively in Australia \
without a licence.

YOUR JOB
You will be given:
  1. A signal fingerprint — numerical measurements describing a captured signal.
  2. ChromaDB nearest neighbours — the most similar signals previously stored,
     with distance scores showing how closely they match.

Use both to classify the signal. Apply your knowledge of the Australian \
frequency band reference below. Explain your reasoning clearly.

{_AU_BAND_REFERENCE}

{_DISTANCE_SCALE_REFERENCE}

OUTPUT FORMAT
Respond with valid JSON only. No prose before or after. No markdown fences. \
No code blocks. Raw JSON exactly matching this schema:

{_JSON_SCHEMA}

If you cannot confidently classify the signal, use signal_type "unknown" \
and set confidence to "low". If all neighbours have distances above 0.052, \
set novel to true.

EVIDENCE PRIORITY (important):
A frequency or ACMA allocation match confirms only that a signal COULD legally \
be present at this frequency — it is NOT evidence that a real signal IS present. \
Noise sitting at an allocated frequency still matches the allocation. Base your \
classification and confidence PRIMARILY on the measured signal characteristics \
(SNR margin, occupied bandwidth, spectral flatness) and the \
vector-store nearest neighbours, which describe what was actually received. \
Treat frequency and ACMA allocation as a SECONDARY plausibility check only. \
If the signal is weak (low SNR margin), occupies essentially no bandwidth \
(single-bin), or is spectrally flat (noise-like), prefer signal_type "noise" \
and set confidence "low" even when the frequency matches a known allocation.

Never invent data — only classify based on what you are given. /no_think"""

    def _build_user_prompt(
        self,
        fingerprint: dict,
        neighbours: list,
        acma_allocations: list[dict] | None = None,
    ) -> str:
        """
        Build the user prompt — constructed fresh for every classification call.

        Annotates raw numbers with plain-English context so the LLM can
        reason about them without needing to know RF conventions itself.

        Args:
            fingerprint     : Phase 2 fingerprint dict.
            neighbours      : Phase 3 ChromaDB query results.
            acma_allocations: ACMA spectrum plan entries covering this
                              frequency, or None/empty to omit.

        Returns:
            Formatted prompt string ready to send to the LLM.
        """
        freq_hz = fingerprint.get("center_freq_hz", 0)
        freq_mhz = freq_hz / 1e6
        peak_db = fingerprint.get("peak_power_db", 0.0)
        snr_db = fingerprint.get("snr_db", 0.0)
        flatness = fingerprint.get("spectral_flatness", 0.0)
        timestamp = fingerprint.get("timestamp", datetime.now().isoformat())
        # Phase 33: bandwidth_hz / occupied_bins / snr_margin_db were computed by
        # fingerprint_spectrum() but never reached the LLM before — the blind spot
        # that let single-bin noise at an allocated frequency pass as a real
        # signal. (peak_bin_power_db / burst structure deliberately NOT surfaced:
        # real FM broadcast trips the 10 dB chunk-vs-average "burst" gap due to
        # audio dynamics, so it does not discriminate pulsed ADS-B from continuous
        # FM as features.py assumes. Re-add only after real ADS-B + FM captures
        # establish the true per-band gap distributions.)
        bandwidth_hz = fingerprint.get("bandwidth_hz", 0.0)
        occupied_bins = fingerprint.get("occupied_bins", 0)
        snr_margin_db = fingerprint.get("snr_margin_db")

        # Annotate SNR with a plain-English quality label
        if snr_db >= 30:
            snr_label = "high — clean capture"
        elif snr_db >= 15:
            snr_label = "moderate"
        else:
            snr_label = "low — signal barely above noise floor"

        # Annotate peak power with a plain-English strength label
        if peak_db >= -30:
            power_label = "strong signal"
        elif peak_db >= -60:
            power_label = "moderate signal"
        else:
            power_label = "weak signal — near noise floor"

        # Annotate spectral flatness
        if flatness <= 0.1:
            flatness_label = "very low = narrow/tonal signal (e.g. FM carrier, LoRa)"
        elif flatness <= 0.4:
            flatness_label = "low-moderate = somewhat structured signal"
        elif flatness <= 0.7:
            flatness_label = "moderate = mixed or wideband signal"
        else:
            flatness_label = "high = noise-like or spread-spectrum signal"

        # Annotate SNR margin — how far above the per-band CALIBRATED detection
        # threshold this signal sits. Small/negative = barely detectable.
        if snr_margin_db is None:
            margin_str = "n/a"
            margin_label = "unknown — margin not supplied"
        else:
            margin_str = f"{snr_margin_db:.1f}"
            if snr_margin_db < 3:
                margin_label = "very low — barely above detection threshold"
            elif snr_margin_db < 10:
                margin_label = "modest — above threshold but not strong"
            else:
                margin_label = "comfortable — well above detection threshold"

        # Annotate occupied bandwidth. A real modulated signal occupies many bins;
        # one or zero bins is a single spike (noise, or an unmodulated carrier).
        if occupied_bins <= 1:
            bandwidth_label = (
                "essentially none — single-bin spike, not an occupied channel"
            )
        else:
            bandwidth_label = f"{occupied_bins} occupied bins — a real channel width"

        # Build neighbours section
        if neighbours:
            neighbour_lines = []
            for i, n in enumerate(neighbours, start=1):
                label = n.get("label", "unknown")
                distance = n.get("distance", 0.0)

                if distance <= 0.004:
                    match_label = "strong match"
                elif distance <= 0.031:
                    match_label = "possible match"
                elif distance <= 0.052:
                    match_label = "different signal type"
                else:
                    match_label = "novel signal — not closely matched to anything stored"

                neighbour_lines.append(
                    f"  {i}. Label: {label:<20} Distance: {distance:.3f}  ({match_label})"
                )
            neighbours_section = "\n".join(neighbour_lines)
        else:
            neighbours_section = "  No neighbours found — signal store may be empty."

        # Build ACMA allocations section if available
        if acma_allocations:
            acma_header = (
                f"ACMA SPECTRUM PLAN -- ALLOCATIONS FOR {freq_mhz:.3f} MHz\n"
                f"The following Australian spectrum allocations cover this frequency:\n"
            )
            acma_lines = [acma_header]
            for idx, alloc in enumerate(acma_allocations, start=1):
                services = ", ".join(alloc.get("services", []))
                band_tag = alloc.get("mimir_band") or "untagged"
                notes = alloc.get("notes", "")
                line = (
                    f"  {idx}. {alloc['freq_start_mhz']}-{alloc['freq_end_mhz']} MHz "
                    f"| Services: {services}\n"
                    f"     Band tag: {band_tag}"
                )
                if notes:
                    line += f"\n     Notes: {notes}"
                acma_lines.append(line)
            acma_section = "\n".join(acma_lines) + "\n"
            acma_footer = (
                "REGULATORY CONTEXT (plausibility check — NOT proof of a real "
                "signal): the ACMA allocations above show what is LICENSED to "
                "operate at this frequency. They confirm whether a classification "
                "is plausible here; they do NOT confirm a real signal is present. "
                "Noise at an allocated frequency still matches the allocation. If "
                "the measured signal evidence is weak or noise-like, keep "
                "confidence LOW even though the frequency sits in a known "
                "allocation.\n"
            )
        else:
            acma_section = ""
            acma_footer = ""

        evidence_order = (
            "HOW TO WEIGH THE EVIDENCE:\n"
            "  1. PRIMARY — the measured signal characteristics (SNR margin, "
            "occupied bandwidth, spectral flatness) and the "
            "vector-store nearest neighbours. These describe what was actually "
            "received.\n"
            "  2. SECONDARY — the centre frequency and any ACMA allocation. These "
            "describe what is expected or permitted here, not what is present.\n"
            "A frequency or allocation match ALONE is not sufficient for high "
            "confidence. High confidence requires the measured evidence to be "
            "consistent with a real signal of the classified type. If the signal "
            "is weak, single-bin, or noise-flat, classify accordingly (often "
            '"noise") and set confidence LOW regardless of the frequency.\n'
        )

        return (
            f"New signal fingerprint:\n"
            f"  Centre frequency  : {freq_hz:,.0f} Hz ({freq_mhz:.3f} MHz)\n"
            f"  Peak power        : {peak_db:.1f} dBFS  ({power_label})\n"
            f"  SNR               : {snr_db:.1f} dB     ({snr_label})\n"
            f"  SNR margin        : {margin_str} dB   ({margin_label})\n"
            f"  Occupied bandwidth: {bandwidth_hz:,.0f} Hz  ({bandwidth_label})\n"
            f"  Spectral flatness : {flatness:.3f}       ({flatness_label})\n"
            f"  Captured          : {timestamp}\n"
            f"\n"
            f"PRIMARY EVIDENCE — ChromaDB nearest neighbours "
            f"(top {len(neighbours)}, lower distance = more similar):\n"
            f"{neighbours_section}\n"
            f"\n"
            f"{acma_section}"
            f"{acma_footer}"
            f"{evidence_order}"
            f"\n"
            f"Classify this signal. Respond with JSON only."
        )

    # ── Response parsing ───────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> ClassificationResult:
        """
        Parse the LLM's raw string response into a ClassificationResult.

        Handles the common case where the LLM wraps its JSON in markdown
        fences (```json ... ```) despite being told not to — some models
        do this anyway. Strips fences before parsing.

        Returns a fallback result if parsing fails for any reason.
        """
        try:
            clean = raw.strip()

            # Strip markdown fences if present — some models add them
            # even when instructed not to
            if clean.startswith("```"):
                lines = clean.split("\n")
                # Drop the opening fence line (```json or ```)
                lines = lines[1:]
                # Drop the closing fence line if present
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()

            data = json.loads(clean)

            return ClassificationResult(
                signal_type=str(data.get("signal_type", "unknown")),
                confidence=str(data.get("confidence", "low")),
                confidence_score=float(data.get("confidence_score", 0.0)),
                novel=bool(data.get("novel", False)),
                reasoning=str(data.get("reasoning", "")),
                au_legal_status=str(data.get("au_legal_status", "verify_before_use")),
                frequency_band=str(data.get("frequency_band", "unknown")),
                raw_response=raw,
            )

        except json.JSONDecodeError as err:
            logger.warning("LLM returned malformed JSON: %s", err)
            return self._fallback_result(
                f"Malformed LLM response — could not parse JSON: {err}",
                raw_response=raw,
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("LLM response had unexpected structure: %s", err)
            return self._fallback_result(
                f"Malformed LLM response — unexpected structure: {err}",
                raw_response=raw,
            )

    # ── Fallback ───────────────────────────────────────────────────────────────

    def _fallback_result(
        self,
        reason: str,
        raw_response: str = "",
    ) -> ClassificationResult:
        """
        Return a safe fallback ClassificationResult when the LLM cannot
        be reached or returns unusable output.

        The fallback result signals to downstream code that classification
        was not possible — without crashing the pipeline.

        Args:
            reason       : Plain English description of why fallback was used.
            raw_response : The raw LLM response string if one was received
                           (empty string if the server was unreachable).
        """
        return ClassificationResult(
            signal_type=self._FALLBACK_SIGNAL_TYPE,
            confidence="low",
            confidence_score=0.0,
            novel=False,
            reasoning=reason,
            au_legal_status="verify_before_use",
            frequency_band="unknown",
            raw_response=raw_response,
        )