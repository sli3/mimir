"""
llm/path_reasoner.py — LLM Trajectory Reasoning for the /radar Page (Phase 53)

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
───────────────────
This module answers a question the physics panel cannot: "does this
aircraft's projected path MAKE SENSE?"

The /radar Path & Trajectory Prediction panel (Phase 52) computes a
dead-reckoning projection — bearing rate and range rate derived from the
stored trail history, extrapolated 45 seconds ahead. That is pure
arithmetic: it cannot notice that the aircraft is squawking an emergency
code, or that it is turning hard enough that a straight-line projection
is meaningless.

This module takes the physics facts, pre-computes the two hard-rule
flags (emergency squawk, high turn rate), and asks the local LLM to
narrate what the aircraft appears to be doing, add nuance the rules
miss, and state its confidence in the 45-second projection.

WHY A SEPARATE MODULE (NOT SignalClassifier)
────────────────────────────────────────────
SignalClassifier is driven continuously by the background scan loop and
carries cooldown state reflecting background-scan failures. This reasoner
is driven by a DELIBERATE human button click on the /radar page — a
different trigger with different latency tolerance (45 s here vs 90 s
for classification) and its own cooldown state, so a background scanning
failure cannot suppress a manual operator request. It deliberately
MIRRORS SignalClassifier's house contracts (never raises, cooldown on
ConnectionError only, markdown fence stripping, fallback result object)
without sharing any state or code with it.
"""

import json
import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


# ── Hard-rule thresholds ──────────────────────────────────────────────────────
# Turn-rate cutoff for the high_turn_rate_flagged rule, in degrees/second.
# 3.0 deg/s is "standard rate" (Rate 1) in aviation — a full 360-degree turn
# in two minutes — the rate airliners fly in holding patterns and procedural
# turns. A SUSTAINED rate at or near standard rate means the aircraft is
# manoeuvring, and a constant-rate straight-line projection 45 s ahead will
# materially over- or under-shoot the turn. The comparison is STRICTLY
# GREATER THAN: an aircraft sitting exactly at the 3.0 deg/s boundary is a
# normal procedural turn and is NOT flagged — flagging the boundary itself
# would cry wolf on every standard-rate hold. The flag tells the LLM
# "treat the linear projection with suspicion", not "something is wrong".
_HIGH_TURN_RATE_DEG_PER_SEC: float = 3.0

# Emergency squawk codes (Mode A transponder). 7500 = unlawful interference
# (hijack), 7600 = radio failure, 7700 = general emergency. These are
# international (ICAO) codes, valid in Australian airspace.
_EMERGENCY_SQUAWKS = frozenset({"7500", "7600", "7700"})

# Allowed confidence tiers. Anything else from the LLM is clamped to "low"
# with a note appended (see _parse_response).
_ALLOWED_CONFIDENCE = frozenset({"high", "medium", "low"})

# JSON schema shown verbatim in the system prompt so the 4B local model
# knows exactly what to return. Three fields only — keep it small.
_JSON_SCHEMA = """
{
  "verdict":    string,  // one short headline line, e.g. "Steady climb on a stable heading"
  "confidence": string,  // "high", "medium", or "low" — your confidence in the 45 s projection
  "notes":      string   // compact caveats or elaboration (one or two sentences)
}
""".strip()


@dataclass
class ReasoningResult:
    """
    The output of a single LLM trajectory-reasoning call.

    Fields
    ──────
    status       : "ok"          = the LLM returned a usable answer.
                   "unavailable" = the call failed for any reason (network,
                                   timeout, malformed JSON, cooldown active).
                                   The endpoint maps this to a structured
                                   200 response; it never surfaces as a 500.

    verdict      : One short headline line from the LLM. On failure this is
                   the distinct sentinel "unavailable" so downstream code
                   (and tests) can tell a fallback apart from a real verdict.

    confidence   : "high" | "medium" | "low". Clamped to this set on parse;
                   any other value the model emits becomes "low" with a note
                   appended to notes.

    notes        : Compact caveats/elaboration from the LLM, or — on failure —
                   a plain-English description of why the call failed.

    raw_response : The raw string the LLM returned. Kept for debugging.
                   Empty string when no response was received.

    cause        : Machine-readable failure cause for the frontend error
                   mapping: "timeout" | "network" | "parse" | "http" |
                   "unknown". None when status is "ok".
    """
    status: str
    verdict: str
    confidence: str
    notes: str
    raw_response: str
    cause: str | None = None


class PathReasoner:
    """
    LLM-based trajectory reasoner for the /radar prediction panel.

    Takes a validated dict of physics facts about one aircraft (built by
    the /api/radar/reason endpoint from the dashboard's physics readout),
    pre-computes the hard-rule flags, calls the local LLM, and returns a
    ReasoningResult.

    Usage:
        reasoner = PathReasoner(
            base_url="http://192.168.0.66:8080/v1",
            model="Qwen3-4B-Mimir",
        )
        result = reasoner.reason(physics_facts)
        print(result.verdict)      # one short headline line
        print(result.confidence)   # "high" | "medium" | "low"

    House contracts mirrored from llm/classifier.py (Phase 22):
      * reason() NEVER raises — it always returns a ReasoningResult.
      * Cooldown is set by ConnectionError ONLY. Timeout, HTTPError, and
        generic exceptions return a fallback but do NOT block future calls.
      * Markdown fences are stripped before json.loads.
      * A malformed response yields a fallback with verdict="unavailable".

    Own instance, own _offline_until: cooldown state is NOT shared with
    SignalClassifier, so a background scanning failure cannot suppress a
    deliberate operator click.
    """

    _FALLBACK_VERDICT = "unavailable"
    _STATUS_OK = "ok"
    _STATUS_UNAVAILABLE = "unavailable"

    def __init__(
        self,
        base_url: str = "http://192.168.0.66:8080/v1",
        model: str = "Qwen3-4B-Mimir",
        temperature: float = 0.1,
        cooldown_sec: float = 60.0,
        timeout_sec: float = 45.0,
        connect_timeout_sec: float = 5.0,
    ) -> None:
        """
        Initialise the reasoner.

        Args:
            base_url    : Base URL of the local LLM server (OpenAI-compatible).
                          Default: Qwen3-4B-Mimir via llama.cpp on yubaba.
            model       : Model name to pass to the API.
            temperature : LLM temperature. Kept low (0.1) like the classifier —
                          narration should be consistent, not creative.
            cooldown_sec: Seconds to suppress LLM retries after a connection
                          failure.
            timeout_sec : Per-request timeout in seconds. 45 s default — much
                          shorter than SignalClassifier's 90 s because this is
                          an interactive UI button; an operator staring at a
                          spinner needs an answer (or a failure) inside a
                          minute, not a minute and a half.
            connect_timeout_sec: Reserved for a future startup health-check
                          probe, mirroring SignalClassifier's constructor
                          shape. Not used by reason() itself.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._cooldown_sec = cooldown_sec
        self._timeout_sec = timeout_sec
        self._connect_timeout_sec = connect_timeout_sec
        self._offline_until: float = 0.0

    # ── Public interface ───────────────────────────────────────────────────────

    def reason(self, physics_facts: dict) -> ReasoningResult:
        """Run an LLM reasoning call over the supplied physics facts.

        Args:
            physics_facts: dict with keys validated by the endpoint:
                icao (str, 6 hex), callsign (str, 1-8 [A-Z0-9 ]),
                squawk (str | None, 4 octal),
                altitude_ft (float), track (float), groundspeed (float),
                vertical_rate (float),
                bearing_deg (float), range_nm (float),
                theta_deg_per_sec (float), delta_r_nm_per_sec (float),
                projected_bearing_deg (float), projected_range_nm (float),
                trail_length (int)

        Returns:
            ReasoningResult — always. Never raises.
            On server error or malformed response, returns a fallback
            result with verdict="unavailable" and confidence="low".

        Note:
            This module performs NO input validation of its own. The caller
            (currently POST /api/radar/reason in dashboard/server.py, via
            _validate_reason_payload) is responsible for type-checking, range-
            bounding, and squawk/callsign/icao charset whitelisting before any
            fact reaches this function. The whitelist is a structural guarantee
            against prompt injection — bypassing it would let attacker-controlled
            text reach the LLM prompt. Do not call reason() with untrusted input.
        """
        # Fast-fail during cooldown — no network call if server known-offline
        if time.time() < self._offline_until:
            return self._fallback_result(
                f"LLM server offline — cooldown active, next retry in "
                f"{max(0.0, self._offline_until - time.time()):.0f} s.",
                cause="network",
            )

        # Prompt construction is INSIDE the try block (unlike classifier.py,
        # which builds prompts outside it): the per-frame ADS-B fields
        # (altitude, track, groundspeed, vertical_rate) legitimately arrive
        # as None on the manual path, and a formatting slip there must
        # degrade to a fallback result, not raise through the endpoint.
        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(physics_facts)

            logger.info(
                "Reasoning over trajectory for ICAO %s via LLM...",
                physics_facts.get("icao", "unknown"),
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
                timeout=self._timeout_sec,
            )
            response.raise_for_status()

            raw = response.json()["choices"][0]["message"]["content"]
            self._offline_until = 0.0  # Server is back — clear cooldown
            logger.debug("LLM raw response: %s", raw)
            return self._parse_response(raw)

        except requests.exceptions.ConnectionError:
            self._offline_until = time.time() + self._cooldown_sec
            logger.warning(
                "LLM server unreachable at %s — cooldown active for %.0f s",
                self._base_url,
                self._cooldown_sec,
            )
            return self._fallback_result(
                f"LLM server unreachable at {self._base_url}.",
                cause="network",
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "LLM server timed out after %s seconds", self._timeout_sec
            )
            # NOTE: Timeout does NOT trigger cooldown — only ConnectionError does.
            # This asymmetry means a timeout will return "unavailable" but not block
            # subsequent requests for the cooldown period. This is intentional per
            # Phase 22 spec: only ConnectionError sets cooldown; Timeout is treated
            # as a transient error without blocking future requests.
            return self._fallback_result(
                f"LLM request timed out after {self._timeout_sec:.0f} seconds.",
                cause="timeout",
            )
        except requests.exceptions.HTTPError as err:
            logger.warning("LLM server returned HTTP error: %s", err)
            return self._fallback_result(
                f"LLM server error — {err}", cause="http"
            )
        except (KeyError, IndexError) as err:
            logger.warning("Unexpected LLM response structure: %s", err)
            return self._fallback_result(
                f"Unexpected LLM response structure — {err}", cause="parse"
            )
        except Exception as err:
            logger.warning("LLM reasoning failed unexpectedly: %s", err)
            return self._fallback_result(
                f"Reasoning unavailable — {err}", cause="unknown"
            )

    # ── Hard-rule flags ────────────────────────────────────────────────────────

    def _emergency_squawk_flagged(self, squawk: str | None) -> bool:
        """True when the squawk is one of the three ICAO emergency codes.

        TD-53-A: AdsbMessage has no `squawk` field (DF4/DF5 surveillance
        replies, where squawk lives, are not decoded by Mimir's PipeDecoder).
        The hard-rule emergency flagging is implemented as defensive code for
        a future where squawk is decoded. Today, squawk is always None from
        real data; the flag never fires. Documented in Phase 53 build report.
        """
        if squawk is None:
            return False
        return str(squawk).strip() in _EMERGENCY_SQUAWKS

    def _high_turn_rate_flagged(self, theta_deg_per_sec: float) -> bool:
        """True when |bearing rate| exceeds the high-turn-rate threshold.

        STRICTLY greater than _HIGH_TURN_RATE_DEG_PER_SEC: exactly 3.0 deg/s
        is a standard-rate (Rate 1) turn — normal procedural flying — and is
        NOT flagged. See the module-level constant for the full rationale.
        A missing or non-numeric rate degrades gracefully to not-flagged:
        never fabricate an alert from absent data.
        """
        try:
            rate = float(theta_deg_per_sec)
        except (TypeError, ValueError):
            return False
        return abs(rate) > _HIGH_TURN_RATE_DEG_PER_SEC

    # ── Prompt construction ────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt — fixed instructions sent with every call.

        Kept compact for the 4B local model: AU legal context header
        (mirroring classifier.py's legal block), a brief role description,
        and the exact three-field JSON schema to return.
        """
        return f"""You are a trajectory-analysis assistant for Mimir, an AI-powered \
passive radio spectrum scanner operating in Adelaide, South Australia, Australia.

LEGAL CONTEXT
You operate under Australian law (Radiocommunications Act 1992, Cth).
This system is receive-only. It never transmits. The aircraft data you \
analyse comes from ADS-B position broadcasts at 1090 MHz, which are legal \
to receive passively in Australia without a licence.

YOUR JOB
You will be given measured facts about one aircraft: its identity, current \
position relative to the receiver (bearing and range), a motion vector \
derived from its recent position history, and a dead-reckoning projection \
45 seconds ahead. Two rule-based flags are PRE-COMPUTED for you — do not \
recompute them:
  * emergency_squawk_flagged — the transponder is squawking 7500, 7600, or 7700.
  * high_turn_rate_flagged   — the bearing rate exceeds \
{_HIGH_TURN_RATE_DEG_PER_SEC:.1f} deg/s, so the straight-line projection \
is likely to over- or under-shoot a manoeuvring aircraft.
Narrate what the aircraft appears to be doing, add any nuance the raw \
numbers and flags miss, and state your confidence in the 45-second \
projection. A projection across a flagged turn, or one built from very \
few trail fixes, deserves LOW confidence.

OUTPUT FORMAT
Respond with valid JSON only. No prose before or after. No markdown fences. \
No code blocks. Raw JSON exactly matching this schema:

{_JSON_SCHEMA}

Never invent data — only reason from the facts you are given. /no_think"""

    def _build_user_prompt(self, facts: dict) -> str:
        """
        Build the user prompt — constructed fresh for every reasoning call.

        Lists the physics facts in plain English so the LLM can reason
        without knowing ADS-B or radar conventions, and appends the two
        pre-computed hard-rule flags. The squawk line is omitted entirely
        when squawk is None (the normal case today — see TD-53-A) so the
        model is not invited to speculate about an absent field.
        """
        icao = str(facts.get("icao", "unknown"))
        callsign = str(facts.get("callsign") or "unknown").upper()
        squawk = facts.get("squawk")

        emergency_flag = self._emergency_squawk_flagged(squawk)
        turn_flag = self._high_turn_rate_flagged(
            facts.get("theta_deg_per_sec", 0.0)
        )

        # None-tolerant formatters: per-frame ADS-B fields arrive as None
        # whenever that frame's typecode did not carry them (velocity and
        # position travel in disjoint typecodes). A missing value renders
        # as "unknown" rather than a fabricated 0.
        def _num(value, fmt):
            if value is None:
                return "unknown"
            try:
                return fmt.format(float(value))
            except (TypeError, ValueError):
                return "unknown"

        def _int(value):
            if value is None:
                return "unknown"
            try:
                return str(int(value))
            except (TypeError, ValueError):
                return "unknown"

        lines = [
            "Aircraft facts:",
            f"  ICAO address        : {icao}",
            f"  Callsign            : {callsign}",
        ]
        if squawk is not None:
            lines.append(f"  Squawk              : {squawk}")
        lines += [
            f"  Altitude            : {_num(facts.get('altitude_ft'), '{:,.0f} ft')}",
            f"  Track               : {_num(facts.get('track'), '{:.0f} deg')}",
            f"  Groundspeed         : {_num(facts.get('groundspeed'), '{:.0f} kt')}",
            f"  Vertical rate       : {_num(facts.get('vertical_rate'), '{:+,.0f} ft/min')}",
            f"  Current position    : bearing "
            f"{_num(facts.get('bearing_deg'), '{:.1f} deg')}, range "
            f"{_num(facts.get('range_nm'), '{:.1f} nm')} from receiver",
            f"  Motion vector       : bearing rate "
            f"{_num(facts.get('theta_deg_per_sec'), '{:+.2f} deg/s')}, "
            f"range rate "
            f"{_num(facts.get('delta_r_nm_per_sec'), '{:+.2f} nm/s')} "
            f"(negative = closing)",
            f"  Projected in 45 s   : bearing "
            f"{_num(facts.get('projected_bearing_deg'), '{:.1f} deg')}, "
            f"range {_num(facts.get('projected_range_nm'), '{:.1f} nm')}",
            f"  Trail fixes used    : {_int(facts.get('trail_length'))}",
            "",
            "Pre-computed rule flags (already determined — do not recompute):",
            f"  emergency_squawk_flagged : {str(emergency_flag).lower()}",
            f"  high_turn_rate_flagged   : {str(turn_flag).lower()}",
            "",
            "Narrate this aircraft's situation and give your confidence in the "
            "45-second projection. Respond with JSON only.",
        ]
        return "\n".join(lines)

    # ── Response parsing ───────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> ReasoningResult:
        """
        Parse the LLM's raw string response into a ReasoningResult.

        Handles the common case where the LLM wraps its JSON in markdown
        fences (```json ... ```) despite being told not to — some models
        do this anyway. Strips fences before parsing.

        Confidence is clamped to {"high", "medium", "low"}: any other value
        becomes "low" with a note appended, so a hallucinated tier can never
        inflate the displayed confidence.

        Returns a fallback result (status "unavailable", cause "parse") if
        parsing fails for any reason.
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

            confidence = str(data.get("confidence", "low")).lower()
            notes = str(data.get("notes", ""))
            if confidence not in _ALLOWED_CONFIDENCE:
                notes = (
                    f"{notes} [confidence clamped: model returned "
                    f"'{confidence}']".strip()
                )
                confidence = "low"

            return ReasoningResult(
                status=self._STATUS_OK,
                verdict=str(data.get("verdict", "")),
                confidence=confidence,
                notes=notes,
                raw_response=raw,
                cause=None,
            )

        except json.JSONDecodeError as err:
            logger.warning("LLM returned malformed JSON: %s", err)
            return self._fallback_result(
                f"Malformed LLM response — could not parse JSON: {err}",
                cause="parse",
                raw_response=raw,
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("LLM response had unexpected structure: %s", err)
            return self._fallback_result(
                f"Malformed LLM response — unexpected structure: {err}",
                cause="parse",
                raw_response=raw,
            )

    # ── Fallback ───────────────────────────────────────────────────────────────

    def _fallback_result(
        self,
        reason: str,
        cause: str,
        raw_response: str = "",
    ) -> ReasoningResult:
        """
        Return a safe fallback ReasoningResult when the LLM cannot be
        reached or returns unusable output.

        The fallback uses the distinct verdict "unavailable" and carries a
        machine-readable cause so the endpoint and frontend can map the
        failure to the right user-facing message — without ever raising.

        Args:
            reason       : Plain English description of why fallback was used.
            cause        : "timeout" | "network" | "parse" | "http" | "unknown".
            raw_response : The raw LLM response string if one was received
                           (empty string if the server was unreachable).
        """
        return ReasoningResult(
            status=self._STATUS_UNAVAILABLE,
            verdict=self._FALLBACK_VERDICT,
            confidence="low",
            notes=reason,
            raw_response=raw_response,
            cause=cause,
        )