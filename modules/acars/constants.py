"""ACARS constants — Australian frequencies and modulation parameters.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

# AU ACARS primary and secondary ground-station frequencies (Hz)
AU_ACARS_FREQUENCIES_HZ = [129_125_000, 130_025_000]

ACARS_BAUD_RATE = 2400.0

# FFSK tone frequencies used in ACARS
ACARS_TONE_0 = 1200.0  # NRZI toggle (bit value flips)
ACARS_TONE_1 = 2400.0  # NRZI no-change (bit value held)

# Preamble length (bits of consecutive 1s before frame sync)
PREAMBLE_BITS = 128

# Frequency tolerance for accepting IQ chunks (Hz)
FREQ_TOLERANCE_HZ = 5_000
