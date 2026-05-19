---
name: python-style
description: Python coding standards for Mimir. Apply automatically whenever writing or reviewing Python files.
---

## Python Style Guide — Mimir RF Scanner

### Standards

#### Imports
Group in this order, separated by blank lines:
```python
# 1. Standard library
import logging
from pathlib import Path

# 2. Third-party
import numpy as np
import SoapySDR

# 3. Local modules
from core.legal.compliance_guard import HardwareTransmitError, transmit_guard
from core.device.hackrf_rx import HackRFReceiver
```

---

#### Type Hints
Always annotate function signatures:
```python
# Correct
def capture_iq(freq_hz: float, duration_sec: float) -> np.ndarray:

# Wrong
def capture_iq(freq_hz, duration_sec):
```

---

#### Docstrings
One line minimum. Always present on every function and class:
```python
def capture_iq(freq_hz: float, duration_sec: float) -> np.ndarray:
    """Capture IQ samples at the given frequency for the specified duration."""
```

---

#### Logging
Always use `logging`, never `print`:
```python
# Correct
logger = logging.getLogger(__name__)
logger.info("Tuning to %.3f MHz", freq_hz / 1e6)

# Wrong
print(f"Tuning to {freq_hz / 1e6} MHz")
```

---

#### Exception Handling
Always catch specific exceptions. Never use bare `except:`:
```python
# Correct
try:
    samples = sdr.read_samples(num_samples)
except RuntimeError as err:
    logger.error("Capture failed: %s", err)
    raise

# Wrong
try:
    samples = sdr.read_samples(num_samples)
except:
    pass
```

---

#### TX Guard Pattern
Any function that must never transmit must call transmit_guard() first:
```python
# Correct
def some_write_adjacent_function(self) -> None:
    """Blocked — TX is illegal without ACMA licence."""
    transmit_guard("some_write_adjacent_function")

# Wrong — no guard
def some_write_adjacent_function(self) -> None:
    pass
```

---

#### File Paths
Always use `pathlib.Path`, never `os.path`:
```python
# Correct
from pathlib import Path
output_path = Path("data") / "capture.npy"
output_path.parent.mkdir(parents=True, exist_ok=True)

# Wrong
import os
output_path = os.path.join("data", "capture.npy")
```

---

#### RF Constants
Always use named constants for frequencies — never bare numbers:
```python
# Correct
FM_CENTRE_HZ = 98_000_000       # 98 MHz FM broadcast
APRS_AU_HZ = 145_175_000        # 145.175 MHz — AU APRS
ISM_AU_HZ = 915_000_000         # 915 MHz — AU/NZ ISM/LoRa (NOT 868 MHz)
ADSB_HZ = 1_090_000_000         # 1090 MHz ADS-B

# Wrong
sdr.set_center_frequency(868000000)   # EU frequency — illegal in AU context
```

---

#### File Header Template
Every new module begins with legal notice:
```python
"""
[module_name].py — [One line description]

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.
"""
import logging

logger = logging.getLogger(__name__)
```

---

### Rules

- Never use `print()` — always `logging`
- Never use bare `except:`
- Never use `os.path` — always `pathlib.Path`
- Never hardcode IPs, credentials, or local paths
- Always add type hints to function signatures
- Always add a docstring to every function and class
- Never use 868 MHz for LoRa (EU band) — always 915 MHz (AU band)
- Never use 144.390 MHz for APRS (US) — always 145.175 MHz (AU)
- All TX-adjacent functions must call transmit_guard() as first line
