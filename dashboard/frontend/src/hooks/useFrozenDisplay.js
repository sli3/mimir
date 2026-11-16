// Frozen AI reasoning display hook, moved out of App.jsx unchanged.

import { useState, useRef, useEffect } from 'react'
import { INITIAL_AI_REASONING } from '../constants/aiReasoning.js'

export default function useFrozenDisplay(aiReasoning) {
  const frozenRef = useRef(null)
  const timerRef = useRef(null)
  const [displayed, setDisplayed] = useState(INITIAL_AI_REASONING)

  useEffect(() => {
    if (!aiReasoning || aiReasoning.signal_type === null) {
      return
    }

    const shouldUpdate =
      aiReasoning.signal_type !== frozenRef.current?.signal_type ||
      timerRef.current === null

    if (shouldUpdate) {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      frozenRef.current = aiReasoning
      setDisplayed(aiReasoning)
      timerRef.current = setTimeout(() => {
        timerRef.current = null
      }, 8000)
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [aiReasoning])

  return displayed
}
