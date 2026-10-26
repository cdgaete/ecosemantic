import { render } from '@testing-library/react'
import { Histogram } from '@/editors/results/figures/Histogram'

it('draws a single visible bar for identical samples with finite axis labels', () => {
  const samples = Array.from({ length: 12 }, () => 5)
  const { container } = render(<Histogram samples={samples} mean={5} median={5} percentiles={[5, 5]} medianCi95={[5, 5]} unit="kg CO2-Eq" />)
  const rects = container.querySelectorAll('rect')
  expect(rects).toHaveLength(1)
  const width = Number(rects[0].getAttribute('width'))
  const height = Number(rects[0].getAttribute('height'))
  expect(width).toBeGreaterThanOrEqual(1)
  expect(Number.isFinite(width)).toBe(true)
  expect(Number.isFinite(height)).toBe(true)
  const axis = container.querySelector('[aria-label="Axis"]')!.textContent!
  expect(axis).toContain('5')
  expect(axis).not.toMatch(/NaN|Infinity/)
})

it('labels the percentiles and the interval of the median for what each is', () => {
  const samples = Array.from({ length: 100 }, (_, i) => i + 1)
  const { container } = render(<Histogram samples={samples} mean={50.5} median={50.5} percentiles={[3.475, 97.525]} medianCi95={[40, 61]} unit="kg" />)
  const labels = Array.from(container.querySelectorAll('ul[aria-label="Markers"] li')).map((t) => t.textContent)
  expect(labels).toContain('2.5th pct')
  expect(labels).toContain('97.5th pct')
  const caption = container.querySelector('figcaption')!.textContent!
  expect(caption).toContain('2.5th to 97.5th percentile 3.48 to 97.53')
  expect(caption).toContain('95 % interval of the median 40 to 61 kg')
})

it('draws the bar of a single value as wide as an ordinary bin, in the middle of the plot', () => {
  const { container } = render(<Histogram samples={[0.0486]} mean={0.0486} median={0.0486} percentiles={[0.0486, 0.0486]} medianCi95={null} unit="mol H+-Eq" />)
  const bar = container.querySelector('rect')!
  const plot = 640 - 40 - 12
  // 24 bins share the plot when samples differ
  expect(Number(bar.getAttribute('width'))).toBeGreaterThanOrEqual(plot / 24 - 1)
  const middle = Number(bar.getAttribute('x')) + Number(bar.getAttribute('width')) / 2
  expect(Math.abs(middle - (40 + plot / 2))).toBeLessThan(1)
  // a median of fewer than six samples has no interval
  expect(container.querySelector('figcaption')!.textContent).toContain('95 % interval of the median – mol H+-Eq')
})
