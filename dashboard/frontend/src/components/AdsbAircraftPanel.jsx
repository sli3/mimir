import React, { useEffect, useState } from 'react'

const MAX_AIRCRAFT = 30

function formatAltitude(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Number(value).toLocaleString()
}

function formatSpeed(value) {
  if (value === null || value === undefined || value === '---') return '—'
  return Math.round(Number(value)).toString()
}

function formatTrack(value) {
  if (value === null || value === undefined || value === '---') return '—'
  const deg = Math.round(Number(value)) % 360
  return `${String(deg).padStart(3, '0')}°`
}

function elapsedSeconds(receivedAt) {
  if (!receivedAt) return '—'
  return Math.floor((Date.now() - receivedAt) / 1000)
}

export default function AdsbAircraftPanel({ adsbAircraft = {}, focusedFreq }) {
  const [now, setNow] = useState(Date.now())
  const isAdsbFreq = focusedFreq && (
    Math.abs(focusedFreq - 1_090_000_000) <= 2_000_000
  )

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const aircraftList = Object.values(adsbAircraft)
    .sort((a, b) => (b.receivedAt || 0) - (a.receivedAt || 0))
    .slice(0, MAX_AIRCRAFT)

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 10,
        color: 'var(--neon-cyan)',
        marginBottom: '8px',
        textShadow: '0 0 6px var(--neon-cyan)',
      }}>
        ADS-B AIRCRAFT
        {aircraftList.length > 0 && (
          <span style={{
            marginLeft: '8px',
            padding: '1px 6px',
            borderRadius: '8px',
            background: 'var(--neon-cyan)',
            color: '#000',
            fontFamily: 'var(--font-data)',
            fontSize: 9,
          }}>
            {aircraftList.length}
          </span>
        )}
      </div>
      {aircraftList.length === 0 ? (
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          {isAdsbFreq
            ? 'Listening on 1090.000 MHz...'
            : 'Not tuned to ADS-B frequency'}
        </div>
      ) : (
        <table style={{
          width: '100%',
          fontFamily: 'var(--font-data)',
          fontSize: 10,
          color: 'var(--text)',
          borderCollapse: 'collapse',
        }}>
          <thead>
            <tr style={{ color: 'var(--neon-cyan)', borderBottom: '1px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Callsign</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>ICAO</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Alt (ft)</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Spd (kt)</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Track (°)</th>
              <th style={{ textAlign: 'left', padding: '2px 4px' }}>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {aircraftList.map((ac) => {
              const displayCallsign = ac.callsign || ac.icao
              const callsignDim = !ac.callsign
              return (
                <tr key={ac.icao} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{
                    padding: '2px 4px',
                    whiteSpace: 'nowrap',
                    color: callsignDim ? 'var(--text-dim)' : 'var(--neon-cyan)',
                  }}>
                    {displayCallsign}
                  </td>
                  <td style={{ padding: '2px 4px', whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
                    {ac.icao}
                  </td>
                  <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                    {formatAltitude(ac.altitude_ft)}
                  </td>
                  <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                    {formatSpeed(ac.groundspeed)}
                  </td>
                  <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                    {formatTrack(ac.track)}
                  </td>
                  <td style={{ padding: '2px 4px', whiteSpace: 'nowrap' }}>
                    {elapsedSeconds(ac.receivedAt)}s
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
