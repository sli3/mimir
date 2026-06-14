"""
Quick diagnostic — prints raw fingerprint features for each band.
Run from project root:
    PYTHONPATH=. python tools/diagnose_fingerprints.py
"""
from core.pipeline.capture import capture_iq
from core.pipeline.fft import compute_psd
from core.pipeline.features import fingerprint_spectrum

# TODO (Phase 9C-Threshold): Gain values below are stale and do not match
# calibrated production gains. Update to match config/mimir.yaml and
# shared_state.py BAND_PROFILES before next run.
# FM_broadcast: should be lna=24, vga=26 (telescopic whip)
# ADS_B: needs revalidation with telescopic whip
# Aviation_VHF: should be lna=16, vga=20
# noise_floor: should be lna=0, vga=0 (zero-gain baseline)
TARGETS = [
    ("FM_broadcast",  98_900_000,    32, 40),  # STALE gains
    ("ADS_B",         1_090_000_000, 32, 38),  # STALE gains
    ("Aviation_VHF",  127_000_000,   32, 40),  # STALE gains
    ("noise_floor",   433_000_000,   16, 20),  # STALE gains
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
