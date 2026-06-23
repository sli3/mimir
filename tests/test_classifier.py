"""
tests/test_classifier.py — Static schema-inspection tests for SignalClassifier

These tests verify that the classifier's internal constants contain the
expected signal type labels and band references. No LLM calls, no network,
no hardware — pure static inspection.
"""

import llm.classifier as classifier_module


def test_acars_in_signal_type_schema():
    """_JSON_SCHEMA must list acars as a valid signal_type value."""
    assert 'acars' in classifier_module._JSON_SCHEMA.lower()


def test_ais_in_signal_type_schema():
    """_JSON_SCHEMA must list ais as a valid signal_type value."""
    assert 'ais' in classifier_module._JSON_SCHEMA.lower()


def test_acars_band_in_frequency_band_schema():
    """_JSON_SCHEMA must list acars_band as a valid frequency_band value."""
    assert 'acars_band' in classifier_module._JSON_SCHEMA.lower()


def test_ais_band_in_frequency_band_schema():
    """_JSON_SCHEMA must list ais_band as a valid frequency_band value."""
    assert 'ais_band' in classifier_module._JSON_SCHEMA.lower()


def test_au_band_reference_contains_acars():
    """_AU_BAND_REFERENCE must describe the ACARS band for correct LLM context."""
    ref = classifier_module._AU_BAND_REFERENCE.lower()
    assert 'acars' in ref
    assert '129' in ref  # 129.125 MHz primary frequency


def test_au_band_reference_contains_ais():
    """_AU_BAND_REFERENCE must describe the AIS band for correct LLM context."""
    ref = classifier_module._AU_BAND_REFERENCE.lower()
    assert 'ais' in ref
    assert '161' in ref  # 161.975 MHz primary AIS channel