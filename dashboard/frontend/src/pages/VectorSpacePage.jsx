import React, { useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Html } from '@react-three/drei'
import './VectorSpacePage.css'

export const VECTOR_COLOUR_MAP = {
  fm_broadcast: '#00f0ff',
  adsb: '#ff2a6d',
  ism_915: '#05ffa1',
  aviation_vhf: '#fcee0a',
  aprs: '#ff8a00',
  acars: '#b400ff',
  ais: '#2d7bff',
  unknown: '#f5f5f5',
}

const FALLBACK_COLOUR = '#888888'

const LABEL_NORMALISATION = {
  fm_broadcast: 'fm_broadcast',
  'fm broadcast': 'fm_broadcast',
  aviation_vhf: 'aviation_vhf',
  'aviation vhf': 'aviation_vhf',
  acars: 'acars',
  aprs: 'aprs',
  ais: 'ais',
  ism_lora: 'ism_915',
  'ism lora': 'ism_915',
  ism_915: 'ism_915',
  ism: 'ism_915',
  ads_b: 'adsb',
  'ads b': 'adsb',
  adsb: 'adsb',
}

export function normaliseLabel(label) {
  const key = String(label ?? 'unknown').toLowerCase().replace(/[^a-z0-9]/g, '_')
  return LABEL_NORMALISATION[key] || key
}

export function getPointColour(label) {
  return VECTOR_COLOUR_MAP[normaliseLabel(label)] || FALLBACK_COLOUR
}

function formatNumber(value) {
  if (value === null || value === undefined) return '---'
  const num = Number(value)
  if (Number.isNaN(num)) return '---'
  return num.toLocaleString('en-AU', { maximumFractionDigits: 2 })
}

function VectorTooltip({ point }) {
  return (
    <div className="vector-tooltip">
      <div className="vector-tooltip-row">
        <span className="vector-tooltip-label">LABEL</span>
        <span className="vector-tooltip-value">{point.label || 'unknown'}</span>
      </div>
      <div className="vector-tooltip-row">
        <span className="vector-tooltip-label">FREQ</span>
        <span className="vector-tooltip-value">{formatNumber(point.frequency_hz)} Hz</span>
      </div>
      <div className="vector-tooltip-row">
        <span className="vector-tooltip-label">SNR</span>
        <span className="vector-tooltip-value">{formatNumber(point.snr_db)} dB</span>
      </div>
      <div className="vector-tooltip-row">
        <span className="vector-tooltip-label">PEAK</span>
        <span className="vector-tooltip-value">{formatNumber(point.peak_power_db)} dB</span>
      </div>
      <div className="vector-tooltip-row">
        <span className="vector-tooltip-label">TIME</span>
        <span className="vector-tooltip-value">{point.timestamp || '---'}</span>
      </div>
    </div>
  )
}

function DataPointComponent({ point, colour }) {
  const [hovered, setHovered] = useState(false)

  return (
    <mesh
      position={[point.x, point.y, point.z]}
      onPointerOver={(event) => {
        event.stopPropagation()
        setHovered(true)
      }}
      onPointerOut={() => setHovered(false)}
    >
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshBasicMaterial
        color={colour}
        transparent
        opacity={0.95}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
      {hovered && (
        <Html distanceFactor={12}>
          <VectorTooltip point={point} />
        </Html>
      )}
    </mesh>
  )
}

const DataPoint = React.memo(DataPointComponent)

const PointsCloud = React.memo(function PointsCloud({ points }) {
  return points.map((point) => (
    <DataPoint key={point.id} point={point} colour={getPointColour(point.label)} />
  ))
})

function Scene({ points }) {
  return (
    <>
      <ambientLight intensity={0.4} />
      <OrbitControls makeDefault target={[0, 0, 0]} />
      <Grid
        position={[0, -10, 0]}
        args={[40, 40]}
        cellSize={1}
        sectionSize={5}
        cellColor="#1a3040"
        sectionColor="#00f0ff"
        fadeDistance={60}
        infiniteGrid
      />
      <PointsCloud points={points} />
    </>
  )
}

function Header({ count, method, status }) {
  const methodText = method ? method.toUpperCase() : 'N/A'
  return (
    <header className="vector-header">
      <div className="vector-header-title">
        <h1>VECTOR SPACE</h1>
        <span className="vector-header-subtitle">ChromaDB embedding visualisation</span>
      </div>
      <div className="vector-header-stats">
        <div className="vector-header-stat">
          <span className="vector-header-stat-label">RECORDS</span>
          <span className="vector-header-stat-value">{count}</span>
        </div>
        <div className="vector-header-stat">
          <span className="vector-header-stat-label">METHOD</span>
          <span className="vector-header-stat-value">{methodText}</span>
        </div>
        <div className="vector-header-stat">
          <span className="vector-header-stat-label">STATUS</span>
          <span className="vector-header-stat-value">{status.toUpperCase()}</span>
        </div>
      </div>
    </header>
  )
}

function Legend() {
  const entries = useMemo(() => Object.entries(VECTOR_COLOUR_MAP), [])
  return (
    <aside className="vector-legend">
      <h2 className="vector-legend-title">BAND LEGEND</h2>
      <ul className="vector-legend-list">
        {entries.map(([key, colour]) => (
          <li key={key} className="vector-legend-item">
            <span className="vector-legend-swatch" style={{ backgroundColor: colour }} />
            <span className="vector-legend-label">{key}</span>
          </li>
        ))}
        <li className="vector-legend-item">
          <span className="vector-legend-swatch" style={{ backgroundColor: FALLBACK_COLOUR }} />
          <span className="vector-legend-label">other</span>
        </li>
      </ul>
    </aside>
  )
}

function LoadingState() {
  return (
    <div className="vector-overlay">
      <div className="vector-message">
        <span className="vector-message-blink">INITIALISING VECTOR STORE PROJECTION...</span>
      </div>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="vector-overlay">
      <div className="vector-message vector-message-error">
        <div>PROJECTION FAILED</div>
        <div className="vector-message-detail">{message || 'Unknown error'}</div>
      </div>
    </div>
  )
}

function EmptyState({ count }) {
  return (
    <div className="vector-overlay">
      <div className="vector-message">
        <div>NOT ENOUGH DATA YET</div>
        <div className="vector-message-detail">
          Current record count: {count}. Run <code>tools/capture_to_vectorstore.py</code> to
          populate the vector store with live RF captures.
        </div>
      </div>
    </div>
  )
}

export default function VectorSpacePage() {
  const [state, setState] = useState({
    status: 'loading',
    points: [],
    count: 0,
    method: null,
    error: null,
  })

  useEffect(() => {
    document.body.classList.add('vector-space-page')
    return () => document.body.classList.remove('vector-space-page')
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/vectorstore/points', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          return response.json().then((body) => {
            throw new Error(body.error || `HTTP ${response.status}`)
          })
        }
        return response.json()
      })
      .then((data) => {
        if (controller.signal.aborted) return
        if (data.status === 'empty') {
          setState({
            status: 'empty',
            points: [],
            count: data.count || 0,
            method: data.method,
            error: null,
          })
        } else {
          setState({
            status: 'ready',
            points: data.points || [],
            count: data.count || 0,
            method: data.method,
            error: null,
          })
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          points: [],
          count: 0,
          method: null,
          error: err.message,
        })
      })

    return () => {
      controller.abort()
    }
  }, [])

  return (
    <div className="vector-page">
      <Header count={state.count} method={state.method} status={state.status} />
      <Legend />
      <div className="vector-canvas-container">
        <Canvas
          camera={{ position: [18, 12, 18], fov: 50 }}
          gl={{ antialias: true, alpha: false }}
          style={{ background: '#080F14' }}
        >
          <Scene points={state.points} />
        </Canvas>
        {state.status === 'loading' && <LoadingState />}
        {state.status === 'error' && <ErrorState message={state.error} />}
        {state.status === 'empty' && <EmptyState count={state.count} />}
      </div>
    </div>
  )
}
