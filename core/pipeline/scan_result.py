from dataclasses import dataclass

from llm.classifier import ClassificationResult


@dataclass
class ScanResult:
    timestamp: str
    center_freq_hz: float
    fingerprint: dict
    classification: ClassificationResult
    psd_db: list | None = None
