/** Shared signal-label normalisation and colours for the vector-space view. */

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

export const FALLBACK_COLOUR = '#888888'

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

/** Normalise a stored signal label to its canonical colour-map key. */
export function normaliseLabel(label) {
  const key = String(label ?? 'unknown').toLowerCase().replace(/[^a-z0-9]/g, '_')
  return LABEL_NORMALISATION[key] || key
}

/** Resolve a signal label to its display colour, with a grey fallback. */
export function getPointColour(label) {
  return VECTOR_COLOUR_MAP[normaliseLabel(label)] || FALLBACK_COLOUR
}
