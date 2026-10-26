export function bins(samples: number[], count: number): { x0: number; x1: number; n: number }[] {
  if (samples.length === 0 || count < 1) return []
  const low = Math.min(...samples)
  const high = Math.max(...samples)
  if (high === low) return [{ x0: low, x1: high, n: samples.length }]
  const width = (high - low) / count
  const out = Array.from({ length: count }, (_, i) => ({ x0: low + i * width, x1: i === count - 1 ? high : low + (i + 1) * width, n: 0 }))
  for (const s of samples) {
    const i = Math.min(count - 1, Math.floor((s - low) / width))
    out[i].n += 1
  }
  return out
}
