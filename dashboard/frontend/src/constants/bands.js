// Band group configuration, moved out of App.jsx unchanged.

export const BAND_GROUPS = [
  {
    label: 'BROADCAST',
    bands: [
      { name: 'FM BROADCAST', freq_hz: 98000000, label: 'FM', band_key: 'fm_broadcast' },
    ],
  },
  {
    label: 'AVIATION BAND',
    bands: [
      { name: 'AVIATION', freq_hz: 127000000, label: 'AVIATION', band_key: 'aviation' },
      { name: 'ACARS', freq_hz: 129125000, label: 'ACARS', band_key: 'acars' },
      { name: 'ADS-B', freq_hz: 1090000000, label: 'ADS-B', band_key: 'adsb' },
    ],
  },
  {
    label: 'MARITIME',
    bands: [
      { name: 'AIS', freq_hz: 162000000, label: 'AIS', band_key: 'ais' },  // 162.000 MHz dual-channel centre
    ],
  },
  {
    label: 'DATA / IoT',
    bands: [
      { name: 'APRS', freq_hz: 145175000, label: 'APRS', band_key: 'aprs' },
      { name: 'ISM', freq_hz: 915000000, label: 'ISM', band_key: 'ism' },
    ],
  },
]
