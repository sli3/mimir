"""ADS-B constants — Australian frequency and demodulation parameters.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

# AU ADS-B Extended Squitter frequency (Hz)
AU_ADSB_FREQUENCY_HZ: int = 1_090_000_000

# Accept anything within 2 MHz of the ADS-B centre frequency
FREQ_TOLERANCE_HZ: int = 2_000_000

# Adelaide receiver reference position.
# NOTE: No longer used for primary position decoding.
# PipeDecoder (modules/adsb/decoder.py) performs global CPR decoding
# without a reference point and does not import these constants.
# Kept here for diagnostic tools and optional fallback use.
ADELAIDE_LAT: float = -34.93
ADELAIDE_LON: float = 138.60

# Aircraft table retention
MAX_AIRCRAFT: int = 30
AIRCRAFT_EXPIRY_SEC: float = 90.0

# Validated range for HackRF One with spiral discone at 1090 MHz: 3.0-6.0.
# Lower values (< 2.0) produce hundreds of noise candidates per chunk with
# zero valid decodes — noise easily satisfies a 1.5 ratio by chance.
# Current value: 8.0 (validated live — HackRF One + spiral discone, Adelaide)
# decrease toward 3.0 only if candidate count drops to zero).
PREAMBLE_THRESHOLD: float = 8.0

# Preamble sample positions at 2 MSa/s (0.5 us per sample)
# ADS-B preamble is 8 us = 16 samples at 2 MSa/s
PREAMBLE_HIGH_INDICES: tuple = (0, 2, 7, 9)
PREAMBLE_LOW_INDICES: tuple = (1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15)

# Message length
PREAMBLE_SAMPLES: int = 16        # 8 us * 2 MSa/s
DATA_BITS: int = 112              # DF17/DF18 long message
DATA_SAMPLES: int = DATA_BITS * 2  # 2 samples per bit at 2 MSa/s
MESSAGE_SAMPLES: int = PREAMBLE_SAMPLES + DATA_SAMPLES  # = 240
