"""
tests/core/soapy_doubles.py
Mimir RF Scanner — SoapySDR test doubles

WHY THIS FILE EXISTS
────────────────────
SoapySDR.Device.enumerate() returns SoapySDRKwargs objects: SWIG wrappers
around a C++ std::map. They are NOT dicts. Verified against real hardware
(HackRF One, 2026-07-17), the available methods are:

    asdict, begin, clear, count, empty, end, erase, find, get_allocator,
    has_key, items, iterator, iteritems, iterkeys, itervalues, key_iterator,
    keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator,
    values

There is NO .get() method.

Mocking enumeration with a plain dict is therefore MORE PERMISSIVE than the
hardware: dicts have .get(), SoapySDRKwargs does not. That gap is not
theoretical. It allowed an AttributeError to ship green through 27 passing
tests in Phase 36, and left PlutoReceiver.open() unable to open its own
device for the entire life of Phase 35 — the failure was invisible because
every test mocked enumeration with dicts and nothing in production called it.

THE RULE
────────
Any test that mocks SoapySDR enumeration must use FakeSoapySDRKwargs, never
a dict. If a future device wrapper is added, its tests must use this double
too.

WHAT dict() ACTUALLY DOES
─────────────────────────
dict(mapping) works by calling keys() and then __getitem__ for each key. That
is why this double implements those two methods: it makes dict(instance)
behave exactly as it does against the real SWIG object, which is the
conversion the production code relies on.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping


class FakeSoapySDRKwargs:
    """Mimics SoapySDR's SWIG-wrapped kwargs object.

    Supports keys(), __getitem__, iteration, items(), values() and has_key()
    so that dict(instance) converts it exactly as the real object does.

    Deliberately has NO .get() method. That omission is the entire purpose of
    this class — do not add one. A .get() here would make the double more
    permissive than the hardware and silently void every test that uses it.
    """

    def __init__(self, mapping: Mapping[str, Any]) -> None:
        self._data: dict[str, Any] = dict(mapping)

    # dict() uses keys() + __getitem__ to convert a mapping.
    def keys(self):
        return self._data.keys()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def has_key(self, key: str) -> bool:
        """Present on the real SWIG object; kept here for fidelity."""
        return key in self._data

    def __repr__(self) -> str:
        return f"FakeSoapySDRKwargs({self._data!r})"