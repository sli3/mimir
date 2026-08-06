import React, { useMemo } from 'react'
import { isValidContact } from './radar/projection.js'
import {
  formatAltitude,
  formatSpeed,
  formatTrack,
  formatVerticalRate,
} from '../utils/aircraftFormat.js'

/**
 * Aircraft detail panel for the /radar page (Phase 51).
 *
 * Sits to the right of RadarScopePanel and provides the "what is that
 * blip?" readout the scope itself cannot show:
 *
 *   a) A scrollable list of every in-range contact, filtered with the
 *      same isValidContact() rule the scope and the page header use
 *      (single source of truth in projection.js - NOT reimplemented
 *      here). Clicking a row selects that aircraft via the
 *      onSelectAircraft(icao) callback; the selected row is highlighted
 *      to match the amber ring the scope draws around the same blip.
 *
 *   b) A pinned, fixed-height (180px) detail card below the list. The
 *      card never resizes: with no selection it renders a placeholder
 *      at the same height, with a selection it swaps in a 2-column
 *      grid - static identity fields on the left (callsign, ICAO hex,
 *      squawk, bearing/range - 4 fields), dynamic per-frame fields
 *      on the right (altitude, track, groundspeed, vertical rate
 *      classification - 4 fields).
 *
 * Every missing/null field renders the em-dash placeholder (U+2014),
 * matching the AdsbAircraftPanel convention via the shared
 * aircraftFormat.js helpers. Passive receive display only - no new
 * data is requested; this panel re-presents what the ADS-B decoder
 * already supplies.
 *
 * @param {Object} adsbAircraft - Map of ICAO address -> aircraft state
 * @param {number} maxRangeNm - Maximum displayed range, in nautical miles
 * @param {string|null} selectedIcao - Currently selected ICAO address
 * @param {Function} onSelectAircraft - Called with the icao string when
 *   a list row is clicked
 */
export default function AircraftDetailPanel({
  adsbAircraft = {},
  maxRangeNm = 40,
  selectedIcao = null,
  onSelectAircraft,
}) {
  // In-range contacts for the scrollable list. Sorted by callsign for
  // a stable row order; aircraft without a callsign sort by ICAO.
  const contacts = useMemo(() => (
    Object.values(adsbAircraft)
      .filter((ac) => isValidContact(ac, maxRangeNm))
      .sort((a, b) => (a.callsign || a.icao).localeCompare(b.callsign || b.icao))
  ), [adsbAircraft, maxRangeNm])

  // The pinned card reads from the full aircraft map, not the filtered
  // list: a selected aircraft that briefly drops out of the valid
  // contact set (e.g. a position-less ADS-B frame) still has identity
  // data worth showing. If the ICAO is gone entirely, treat it as no
  // selection.
  const selected = selectedIcao ? (adsbAircraft[selectedIcao] ?? null) : null

  // Groundspeed carries its unit suffix in the list rows ("450kt");
  // when the value is missing the shared formatter already returns the
  // em-dash, which must NOT gain a suffix.
  const speedWithUnit = (value) => {
    const formatted = formatSpeed(value)
    return formatted === '—' ? formatted : `${formatted}kt`
  }

  // Combined bearing/range readout (Phase 55). Bearing rounds to whole
  // degrees and zero-pads to three characters ("005°", "045°"); range
  // renders to one decimal ("12.3nm"). If EITHER input is missing the
  // whole field falls back to the em-dash placeholder - a partial
  // readout would imply precision the data does not have.
  const formatBearingRange = (bearing, range) => {
    if (bearing === null || bearing === undefined) return '—'
    if (range === null || range === undefined) return '—'
    const padded = String(Math.round(bearing)).padStart(3, '0')
    return `${padded}° / ${range.toFixed(1)}nm`
  }

  return (
    <div className="radar-detail-panel">
      <div className="radar-detail-list-header">
        <span>CALLSIGN</span>
        <span>ALT</span>
        <span>TRK</span>
        <span>SPD</span>
      </div>
      <div className="radar-detail-list">
        {contacts.length === 0 ? (
          <div className="radar-detail-list-empty">No in-range contacts</div>
        ) : (
          contacts.map((ac) => (
            <div
              key={ac.icao}
              data-testid="radar-detail-row"
              data-icao={ac.icao}
              className={
                ac.icao === selectedIcao
                  ? 'radar-detail-row radar-detail-row-selected'
                  : 'radar-detail-row'
              }
              onClick={() => onSelectAircraft?.(ac.icao)}
            >
              <span>{ac.callsign || '—'}</span>
              <span>{formatAltitude(ac.altitude_ft)}</span>
              <span>{formatTrack(ac.track)}</span>
              <span>{speedWithUnit(ac.groundspeed)}</span>
            </div>
          ))
        )}
      </div>
      <div className="radar-detail-pinned" data-testid="radar-detail-pinned">
        {!selected ? (
          <div className="radar-detail-pinned-placeholder">
            No aircraft selected
          </div>
        ) : (
          <div className="radar-detail-grid">
            <div className="radar-detail-column">
              <div className="radar-detail-field">
                <span className="radar-detail-label">Callsign</span>
                <span className="radar-detail-value">{selected.callsign || '—'}</span>
              </div>
              <div className="radar-detail-field">
                <span className="radar-detail-label">ICAO</span>
                <span className="radar-detail-value">{selected.icao ?? '—'}</span>
              </div>
              <div className="radar-detail-field">
                <span className="radar-detail-label">Squawk</span>
                <span className="radar-detail-value">{selected.squawk ?? '—'}</span>
              </div>
              {/* 4th static-column slot filled in Phase 55 with the
                  combined bearing/range readout. Both columns now carry
                  4 fields each; the Phase 51 "unevenness is per spec"
                  claim is removed. */}
              <div className="radar-detail-field">
                <span className="radar-detail-label">Bearing / Range</span>
                <span className="radar-detail-value">
                  {formatBearingRange(selected.bearing_deg, selected.range_nm)}
                </span>
              </div>
            </div>
            <div className="radar-detail-column">
              <div className="radar-detail-field">
                <span className="radar-detail-label">Altitude (ft)</span>
                <span className="radar-detail-value">{formatAltitude(selected.altitude_ft)}</span>
              </div>
              <div className="radar-detail-field">
                <span className="radar-detail-label">Track</span>
                <span className="radar-detail-value">{formatTrack(selected.track)}</span>
              </div>
              <div className="radar-detail-field">
                <span className="radar-detail-label">Groundspeed</span>
                <span className="radar-detail-value">{speedWithUnit(selected.groundspeed)}</span>
              </div>
              <div className="radar-detail-field">
                <span className="radar-detail-label">Vertical rate</span>
                <span className="radar-detail-value">{formatVerticalRate(selected.vertical_rate)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
