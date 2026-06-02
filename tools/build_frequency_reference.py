"""
tools/build_frequency_reference.py

Converts the raw pdfplumber extraction of the ACMA Radiofrequency Spectrum Plan
into a clean, structured frequency_reference_raw.json file.

This is a one-off data pipeline script. Run it once, review the output,
then copy the reviewed file to data/frequency_reference.json.

Usage:
    python tools/build_frequency_reference.py \\
        acma_tables_plumber.json \\
        data/frequency_reference_raw.json

Input:
    acma_tables_plumber.json — produced by tools/inspect_acma_pdf.py

Output:
    frequency_reference_raw.json — 432 entries covering HackRF range (1–6000 MHz)
    Each entry:
    {
        "freq_start_mhz": 87.5,
        "freq_end_mhz":   108.0,
        "services":       ["BROADCASTING", "Fixed", "Mobile"],
        "footnotes":      ["AUS103"],
        "mimir_band":     "fm_broadcast",       // only on our 5 key bands
        "notes":          ""                    // blank — fill in manually
    }

Requirements:
    pip install pdfplumber  (already installed if you ran inspect_acma_pdf.py)
    No other dependencies — this script only reads JSON.

Review process after running:
    1. Open frequency_reference_raw.json
    2. Search for each of the 5 Mimir bands and confirm services look right:
       - 87.5–108 MHz  → BROADCASTING
       - 117.975–137   → AERONAUTICAL MOBILE (R)
       - 144–146 MHz   → AMATEUR / AMATEUR-SATELLITE  (APRS sits inside this)
       - 915–928 MHz   → RADIOLOCATION / Fixed / Mobile  (ISM class licence)
       - 960–1164 MHz  → AERONAUTICAL MOBILE (R)  (ADS-B sits at 1090)
    3. Fix any obvious service name errors you spot (merged lines, etc.)
    4. Copy to data/frequency_reference.json when satisfied
"""

import sys
import json
import re
import pathlib


# ── Regexes ────────────────────────────────────────────────────────────────────

# Matches the first line of an AU column cell: "87.5 – 108"
# Handles non-breaking spaces, en-dashes, hyphens, and narrow spaces.
FREQ_RANGE_RE = re.compile(
    r'^([\d\s\u00a0]+(?:\.\d+)?)\s*[–\-\u2013]\s*([\d\s\u00a0]+(?:\.\d+)?)\s*\n'
)

# Standalone ITU or AU footnote references that appear as their own line.
# Examples: "AUS103", "AUS101A", "198A", "64", "111"
FOOTNOTE_ONLY_RE = re.compile(
    r'^(AUS\d+[A-Z]?|(?:\d+[A-Z]{0,2}))$'
)

# Lines that are continuations of the preceding service name, not new services.
# These arise from PDF line-wrapping inside a single cell.
# Examples: "(R)", "(OR)", "(space-to-Earth)", "SATELLITE (R) 198A 198B"
CONTINUATION_STARTERS = (
    '(R)',
    '(OR)',
    '(R) ',
    '(OR) ',
    'SATELLITE',
    'SATELLITE ',
    'to-Earth)',
    'to-space)',
    'space-to-',
    'Earth-to-',
    '(space-to-',
    '(Earth-to-',
)

# Numbers-only lines that are footnote run-ons, e.g. "111 200 AUS25 AUS103"
# These appear at the end of a cell when multiple footnotes wrap onto one line.
MULTI_FOOTNOTE_RE = re.compile(
    r'^((?:AUS\d+[A-Z]?|\d+[A-Z]{0,2})\s+)+(?:AUS\d+[A-Z]?|\d+[A-Z]{0,2})$'
)

# ── Mimir band labelling ───────────────────────────────────────────────────────
# We tag entries that contain one of our 5 key AU frequencies.
# This makes the LLM's job easier: it can do an exact lookup first,
# then fall back to range search for unlabelled entries.

MIMIR_BANDS = [
    ('fm_broadcast',    87.5,    108.0),
    ('aviation_vhf',   117.975, 137.0),
    ('aprs',           144.0,   146.0),   # APRS at 145.175 sits inside amateur band
    ('ism_lora',       915.0,   928.0),   # AU ISM class licence range
    ('adsb',           960.0,  1164.0),   # ADS-B at 1090 sits inside this
]


def label_band(freq_start, freq_end):
    """Return a Mimir band label if this entry covers one of our 5 key bands."""
    for band_name, band_start, band_end in MIMIR_BANDS:
        # Entry overlaps with band if ranges intersect
        if freq_start <= band_end and freq_end >= band_start:
            return band_name
    return None


# ── Service line parser ────────────────────────────────────────────────────────

def parse_lines(lines):
    """
    Split raw cell lines into (services, footnotes).

    The ACMA table wraps long service names across multiple PDF lines.
    For example:
        'AERONAUTICAL MOBILE-'   ← wrapped mid-name
        'SATELLITE (R) 198A 198B' ← continuation

    We detect continuations and stitch them back onto the preceding service.
    Footnote-only lines and multi-footnote run-on lines are separated out.
    """
    services = []
    footnotes = []
    buf = None   # accumulator for current service name being built

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Pure footnote line: "AUS103", "198A", "64"
        if FOOTNOTE_ONLY_RE.match(line):
            if buf:
                services.append(buf)
                buf = None
            footnotes.append(line)
            continue

        # Multi-footnote run-on: "111 200 AUS25 AUS103"
        if MULTI_FOOTNOTE_RE.match(line):
            if buf:
                services.append(buf)
                buf = None
            # Split and add each as a separate footnote
            for token in line.split():
                footnotes.append(token)
            continue

        # Continuation of previous service name (PDF wrapped the line mid-word)
        is_continuation = (
            buf is not None and (
                buf.endswith('-') or          # hyphenated wrap: "MOBILE-" → "SATELLITE"
                buf.endswith('(') or          # open bracket: "MOBILE ("
                line.startswith(tuple(CONTINUATION_STARTERS))
            )
        )

        if is_continuation:
            # Join with a space, but no space if previous ended with hyphen
            if buf.endswith('-'):
                buf = buf + line
            else:
                buf = buf + ' ' + line
        else:
            # New service — flush buffer first
            if buf:
                services.append(buf)
            buf = line

    # Flush final buffer
    if buf:
        services.append(buf)

    # Post-process: strip trailing footnote numbers from service strings.
    # E.g. "MOBILE 314A 317A" → service="MOBILE", footnotes=["314A", "317A"]
    clean_services = []
    for svc in services:
        parts = svc.split()
        # Walk from the end, pulling off anything that looks like a footnote
        trailing_footnotes = []
        while parts and FOOTNOTE_ONLY_RE.match(parts[-1]):
            trailing_footnotes.insert(0, parts.pop())
        footnotes.extend(trailing_footnotes)
        rejoined = ' '.join(parts).strip()
        if rejoined:
            clean_services.append(rejoined)

    return clean_services, footnotes


# ── Main extraction loop ───────────────────────────────────────────────────────

def extract_entries(plumber_tables):
    """
    Walk all pdfplumber tables, extract AU column cells (index 3),
    parse each cell, deduplicate, filter to HackRF range, and return
    a sorted list of allocation entries.
    """
    seen_keys = set()
    entries = []

    for table in plumber_tables:
        rows = table.get('data', [])
        # Rows 0 and 1 are always header rows — skip them
        for row in rows[2:]:
            # AU allocation is always in column index 3
            if len(row) < 4:
                continue
            au_cell = row[3]
            if not au_cell:
                continue

            au_cell = au_cell.strip()

            # Must start with a frequency range
            m = FREQ_RANGE_RE.match(au_cell)
            if not m:
                continue

            # Parse frequency range — remove narrow/non-breaking spaces
            try:
                freq_start = float(m.group(1).replace('\u00a0', '').replace(' ', ''))
                freq_end   = float(m.group(2).replace('\u00a0', '').replace(' ', ''))
            except ValueError:
                continue

            # Filter: HackRF One covers 1 MHz to 6 GHz
            if freq_end < 1.0 or freq_start > 6000.0:
                continue

            # Deduplicate: same frequency range may appear across page-spanning tables
            key = (freq_start, freq_end)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Parse the rest of the cell: service names and footnotes
            remainder = au_cell[m.end():].strip()
            raw_lines = [l.strip() for l in remainder.split('\n') if l.strip()]
            services, footnotes = parse_lines(raw_lines)

            mimir_band = label_band(freq_start, freq_end)

            entries.append({
                'freq_start_mhz': freq_start,
                'freq_end_mhz':   freq_end,
                'services':       services,
                'footnotes':      sorted(set(footnotes)),   # dedupe footnotes too
                'mimir_band':     mimir_band,
                'notes':          '',
            })

    # Sort by start frequency
    entries.sort(key=lambda e: e['freq_start_mhz'])
    return entries


# ── Validation report ──────────────────────────────────────────────────────────

def validate(entries):
    """Print a sanity-check report for the 5 Mimir bands."""
    print("\n[ Mimir band validation ]")
    print("-" * 50)

    checks = [
        ('FM broadcast',  98.0,     'BROADCASTING'),
        ('Aviation VHF',  127.0,    'AERONAUTICAL MOBILE'),
        ('APRS band',     145.175,  'AMATEUR'),
        ('ISM / LoRa',    915.0,    'RADIOLOCATION'),
        ('ADS-B',         1090.0,   'AERONAUTICAL'),
    ]

    for label, freq, expected_keyword in checks:
        hits = [
            e for e in entries
            if e['freq_start_mhz'] <= freq <= e['freq_end_mhz']
            and e['mimir_band'] is not None
        ]
        if not hits:
            print(f"  ⚠  {label} ({freq} MHz): NO ENTRY FOUND")
            continue
        for h in hits:
            svc_str = ', '.join(h['services'])
            ok = expected_keyword.upper() in svc_str.upper()
            symbol = '✓' if ok else '⚠'
            print(f"  {symbol}  {label}: {h['freq_start_mhz']}–{h['freq_end_mhz']} MHz")
            print(f"     Services : {h['services']}")
            print(f"     Footnotes: {h['footnotes']}")
            print(f"     Band tag : {h['mimir_band']}")

    print()
    print(f"  Total entries (HackRF range 1–6000 MHz): {len(entries)}")
    print(f"  Mimir-tagged entries: {sum(1 for e in entries if e['mimir_band'])}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python tools/build_frequency_reference.py "
            "<acma_tables_plumber.json> <output.json>"
        )
        sys.exit(1)

    input_path  = pathlib.Path(sys.argv[1])
    output_path = pathlib.Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    print(f"Reading: {input_path}")
    with open(input_path, encoding='utf-8') as f:
        plumber_tables = json.load(f)

    print(f"Tables in input: {len(plumber_tables)}")

    entries = extract_entries(plumber_tables)

    validate(entries)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"Written: {output_path}")
    print()
    print("Next steps:")
    print("  1. Open the output JSON and review the 5 Mimir band entries")
    print("  2. Fix any service names that look wrong (check 'notes' field)")
    print("  3. Copy to data/frequency_reference.json when satisfied")


if __name__ == '__main__':
    main()
