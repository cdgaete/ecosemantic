import { render } from '@testing-library/react'
import { useRef } from 'react'
import { useClearance, useIslandClearance } from '@/window/clearance'

function Frame({ island, held }: { island: boolean; held: boolean }) {
  const frame = useRef<HTMLDivElement>(null)
  useIslandClearance(frame, island ? 'with the island' : 'without it', held)
  return <div ref={frame}>{island ? <div data-clear="right" /> : null}</div>
}

const right = () => useClearance.getState().clearance.right

describe('a frame whose islands leave', () => {
  beforeEach(() => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      const left = (this as HTMLElement).dataset.clear === undefined ? 0 : 700
      return { left, top: 0, right: 1000, bottom: 800, width: 1000 - left, height: 800, x: left, y: 0, toJSON: () => ({}) }
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('measures again and clears only the gap', () => {
    const view = render(<Frame island held={false} />)
    // the island reaches 300 px in from the right, and the gap is 12
    expect(right()).toBe(312)
    view.rerender(<Frame island={false} held={false} />)
    expect(right()).toBe(12)
  })

  it('keeps the clearance it had while it is held', () => {
    const view = render(<Frame island held={false} />)
    expect(right()).toBe(312)
    view.rerender(<Frame island={false} held />)
    expect(right()).toBe(312)
    view.rerender(<Frame island held={false} />)
    expect(right()).toBe(312)
  })
})
