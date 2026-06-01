import { useEffect, useState } from 'react'

export function useCanvasSize(canvasRef) {
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const el = canvasRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        const w = Math.floor(width)
        const h = Math.floor(height)
        el.width = w
        el.height = h
        setSize({ width: w, height: h })
      }
    })

    observer.observe(el)

    return () => {
      observer.disconnect()
    }
  }, [canvasRef])

  return size
}
