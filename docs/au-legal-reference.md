# Australian RF Legal Reference
## Mimir RF Scanner — ACMA Compliance Document

**Jurisdiction**: Australia — South Australia (Adelaide)
**Authority**: ACMA (Australian Communications and Media Authority)
**Law**: Radiocommunications Act 1992 (Cth)
**Last reviewed**: 2026

---

## The Single Most Important Rule

**Passive reception of radio signals requires no licence in Australia.**
You can legally listen to (receive) any radio signal you can detect.

**Transmitting without a licence is a criminal offence.**
Under the Radiocommunications Act 1992 (Cth), operating a transmitter
without an apparatus licence can result in significant penalties.
This project holds no apparatus licence. Therefore no transmission
code exists anywhere in this codebase.

---

## What "Passive Receive" Means

Your HackRF One is a radio receiver when used in this project. It:
- Detects radio waves already present in the air
- Converts them to digital data your computer can analyse
- Does not broadcast, emit, or add any signal to the spectrum

This is legally equivalent to listening to a radio. The radio station
is broadcasting whether you listen or not. Your receiver adds nothing
to the environment.

---

## Frequencies Legal to Receive in Australia

All frequencies listed below carry signals that are publicly broadcast.
Reception is legal and requires no licence.

### FM Broadcast (87.5–108 MHz)
Commercial and community radio stations. Broadcast under their own
licences for public reception. Adelaide stations include Mix 102.3,
SAFM, ABC Adelaide, Triple J, and others.

### Aviation VHF (118–136 MHz)
Air traffic control communications and aircraft position reports.
Broadcast openly for aviation safety. LiveATC.net streams these
publicly as a reference point for their legality to receive.

### APRS — 145.175 MHz (Australian frequency)
Automatic Packet Reporting System. Amateur radio operators broadcast
their GPS positions, weather data, and messages on this frequency.
**Important**: The Australian APRS frequency is **145.175 MHz**.
The US frequency is 144.390 MHz. Never assume US frequencies apply here.

### ISM / LoRa — 915 MHz (Australian/NZ band)
Industrial, Scientific, and Medical band. Used by LoRa IoT devices,
some wireless sensors, and other low-power devices.
**Important**: The Australian ISM/LoRa band is **915 MHz**.
The European band is 868 MHz. Do not assume EU frequencies apply here.

### ADS-B — 1090 MHz
Automatic Dependent Surveillance-Broadcast. All commercial and most
private aircraft broadcast their GPS position, altitude, speed, heading,
and flight number on 1090 MHz continuously and unencrypted. This is
mandated by CASA (Civil Aviation Safety Authority) for aviation safety.
Services like FlightAware and Flightradar24 are built entirely on
ADS-B reception, confirming its fully public legal status.

---

## What This Project Does NOT Do

- Does not transmit on any frequency
- Does not decode encrypted communications
- Does not intercept private communications (all signals decoded are
  public broadcast signals)
- Does not store or forward communications content

---

## ACMA Contact and Further Information

- ACMA website: https://www.acma.gov.au
- Radiocommunications licensing: https://www.acma.gov.au/licences
- Australian radiofrequency spectrum plan:
  https://www.acma.gov.au/australian-radiofrequency-spectrum-plan

---

## Disclaimer

This document is a project reference summary, not legal advice.
If you have specific questions about Australian radio law, consult
a qualified legal professional or contact ACMA directly.
