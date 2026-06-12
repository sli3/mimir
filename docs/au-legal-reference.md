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

### ACARS — 129.125 MHz / 130.025 MHz (Australian primary frequencies)
Aircraft Communications Addressing and Reporting System. A digital
messaging protocol used by aircraft to exchange short operational data
with ground stations — engine readings, flight plan updates, weather
information, and clearances. Messages are transmitted over VHF radio
using AM modulation with FSK data encoding.

ACARS is distinct from ADS-B:
- ADS-B (1090 MHz) broadcasts GPS position continuously and automatically
- ACARS (VHF) exchanges operational messages on demand

Both are passive receive only. ACARS operates within the VHF aviation
band (118–136 MHz) already covered by the existing ACMA allocation.
Specific channel assignments at 129.125 MHz and 130.025 MHz are made
by ICAO and Airservices Australia within that allocation.

Reception is legal under the Radiocommunications Act 1992 (Cth).
No licence required. ACMA authority applies.

### AIS — 161.975 MHz / 162.025 MHz (Australian maritime VHF)
Automatic Identification System. A digital data link used by ships and
vessels to broadcast their identity, position, course, speed, and other
navigational data. AIS operates on two VHF channels (161.975 MHz and
162.025 MHz) using GMSK modulation at 9600 baud. All commercial vessels
over 300 gross tonnage and passenger vessels are required to transmit
AIS data under International Maritime Organization (IMO) SOLAS regulations.

AIS is a public broadcast safety system — the data is transmitted
unencrypted and intended to be received by all vessels and shore stations
in range. Services like MarineTraffic and VesselFinder are built entirely
on AIS reception, confirming its fully public legal status.

Reception is legal under the Radiocommunications Act 1992 (Cth).
No licence required. ACMA authority applies.
Transmission requires an AMSA-issued maritime radio licence.

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
