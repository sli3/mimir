# modules/_base/module_base.py
# Mimir RF Scanner — Signal Module Base Class (stub)
#
# Phase 1+ will define the full interface here.
# Each signal module (ADS-B, APRS, FM, etc.) will subclass this.

from abc import ABC, abstractmethod


class SignalModuleBase(ABC):
    """Base class for all Mimir signal analysis modules. Stub — Phase 1."""

    @abstractmethod
    def name(self) -> str:
        """Return the module name (e.g. 'adsb', 'aprs', 'fm')."""
        ...

    @abstractmethod
    def process(self, samples):
        """Process IQ samples and return decoded signal data."""
        ...
