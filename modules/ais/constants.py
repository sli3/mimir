"""AIS constants — Australian frequencies and modulation parameters.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

# AU AIS maritime VHF frequencies (Hz)
AU_AIS_CENTRE_FREQ_HZ = 162_000_000
AU_AIS_CH1_HZ = 161_975_000
AU_AIS_CH2_HZ = 162_025_000

AIS_BAUD_RATE = 9600

# Frequency tolerance for accepting IQ chunks (Hz)
# Set to 100 kHz to capture both channels (±25 kHz from centre) with margin
FREQ_TOLERANCE_HZ = 100_000

# Channel offsets from centre frequency for dual-channel reception
CH1_OFFSET_HZ = -25_000
CH2_OFFSET_HZ = +25_000
