"""
Quick diagnostic — prints raw fingerprint features for each band.
Run from project root:
    PYTHONPATH=. python tools/diagnose_fingerprints.py
"""
from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum

# Gain values match production BAND_PROFILES in dashboard/shared_state.py.
# FM_broadcast and ADS_B calibrated for telescopic whip (Phase 9C-Threshold).
# ACARS and Aviation_VHF use moderate gain — weaker signals at VHF.
# APRS, ISM, and AIS use same gain as FM — telescopic whip couples well here.
# noise_floor uses moderate gain (16/20) for diagnostic visibility.
TARGETS = [
    ("FM_broadcast",  98_900_000,     24, 26),  # calibrated: telescopic whip, Phase 9C-Threshold
    ("Aviation_VHF",  127_000_000,    16, 20),  # provisional: not yet validated with telescopic whip
    ("ACARS",         129_125_000,    16, 20),  # provisional: not yet validated with telescopic whip
    ("APRS",          145_175_000,    24, 26),  # calibrated threshold: 10 dB, 2026-06-24
    ("AIS",           162_000_000,    24, 26),  # provisional: not yet validated with telescopic whip
    ("ISM_LoRa",      915_000_000,    24, 26),  # calibrated threshold: 3 dB, 2026-06-24
    ("ADS_B",         1_090_000_000,  24, 24),  # calibrated: telescopic whip, Phase 9C-Threshold
    ("noise_floor",   433_000_000,    16, 20),  # moderate gain for diagnostic visibility
]

for label, freq_hz, lna, vga in TARGETS:
    print(f"\nCapturing {label} @ {freq_hz / 1e6:.1f} MHz ...")
    samples = capture_iq(
        freq_hz=freq_hz,
        num_samples=256_000,
        sample_rate_hz=2_000_000,
        lna_gain_db=lna,
        vga_gain_db=vga,
    )
    psd = compute_psd(samples, 2_000_000, freq_hz)
    fp  = fingerprint_spectrum(psd)
    print(f"  {'key':<22} value")
    print(f"  {'-'*40}")
    for k, v in fp.items():
        print(f"  {k:<22} {v}")
