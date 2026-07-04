"""
Quick diagnostic — prints raw fingerprint features for each band.
Run from project root:
    PYTHONPATH=. python tools/diagnose_fingerprints.py
"""
from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum
from dashboard.shared_state import BAND_PROFILES

# Gain values (except noise_floor) are read live from
# dashboard.shared_state.BAND_PROFILES so diagnostic captures use the same
# gains as the live dashboard. signal_threshold_db is also read from
# BAND_PROFILES so the fingerprint output reflects live settings.
# noise_floor uses moderate gain (16/20) for diagnostic visibility and is
# intentionally NOT sourced from BAND_PROFILES['noise_floor'] (0/0).
TARGETS = [
    ("FM_broadcast",  98_900_000,     BAND_PROFILES["fm_broadcast"]["lna_gain_db"], BAND_PROFILES["fm_broadcast"]["vga_gain_db"], BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]),
    ("Aviation_VHF",  127_000_000,    BAND_PROFILES["aviation"]["lna_gain_db"], BAND_PROFILES["aviation"]["vga_gain_db"], BAND_PROFILES["aviation"]["signal_threshold_db"]),
    ("ACARS",         129_125_000,    BAND_PROFILES["acars"]["lna_gain_db"], BAND_PROFILES["acars"]["vga_gain_db"], BAND_PROFILES["acars"]["signal_threshold_db"]),
    ("APRS",          145_175_000,    BAND_PROFILES["aprs"]["lna_gain_db"], BAND_PROFILES["aprs"]["vga_gain_db"], BAND_PROFILES["aprs"]["signal_threshold_db"]),
    ("AIS",           162_000_000,    BAND_PROFILES["ais"]["lna_gain_db"], BAND_PROFILES["ais"]["vga_gain_db"], BAND_PROFILES["ais"]["signal_threshold_db"]),
    ("ISM_LoRa",      915_000_000,    BAND_PROFILES["ism"]["lna_gain_db"], BAND_PROFILES["ism"]["vga_gain_db"], BAND_PROFILES["ism"]["signal_threshold_db"]),
    ("ADS_B",         1_090_000_000,  BAND_PROFILES["adsb"]["lna_gain_db"], BAND_PROFILES["adsb"]["vga_gain_db"], BAND_PROFILES["adsb"]["signal_threshold_db"]),
    ("noise_floor",   433_000_000,    16, 20, 10.0),  # intentionally NOT from BAND_PROFILES['noise_floor'] (0,0)
]

for label, freq_hz, lna, vga, threshold in TARGETS:
    print(f"\nCapturing {label} @ {freq_hz / 1e6:.1f} MHz ...")
    samples = capture_iq(
        freq_hz=freq_hz,
        num_samples=256_000,
        sample_rate_hz=2_000_000,
        lna_gain_db=lna,
        vga_gain_db=vga,
    )
    psd = compute_psd(samples, 2_000_000, freq_hz)
    fp  = fingerprint_spectrum(psd, signal_threshold_db=threshold)
    print(f"  {'key':<22} value")
    print(f"  {'-'*40}")
    for k, v in fp.items():
        print(f"  {k:<22} {v}")

# NOTE: The top-level loop runs on import (pre-existing). Wrap in
# if __name__ == "__main__": in a future refactor to avoid hardware
# capture during testing.