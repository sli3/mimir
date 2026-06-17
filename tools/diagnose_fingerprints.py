"""
Quick diagnostic — prints raw fingerprint features for each band.
Run from project root:
    PYTHONPATH=. python tools/diagnose_fingerprints.py
"""
from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum

# Gain values: FM_broadcast calibrated to telescopic whip (Phase 9C-Threshold).
# Aviation_VHF matches production BAND_PROFILES defaults (not yet validated
# with telescopic whip). ADS_B uses provisional stock-stub values — requires
# recalibration with telescopic whip. noise_floor uses moderate gain (16/20)
# for diagnostic visibility, unlike the production zero-gain baseline used by
# calibrate_thresholds.py and shared_state.py.
TARGETS = [
    ("FM_broadcast",  98_900_000,    24, 26),  # calibrated: telescopic whip
    ("ADS_B",         1_090_000_000, 32, 38),  # TODO: recalibrate with telescopic whip — provisional stock-stub values
    ("Aviation_VHF",  127_000_000,   16, 20),  # provisional: matches BAND_PROFILES defaults, not yet validated with telescopic whip
    ("noise_floor",   433_000_000,   16, 20),  # moderate gain for diagnostic visibility
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
