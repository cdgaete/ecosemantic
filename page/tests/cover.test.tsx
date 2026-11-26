import { render } from '@testing-library/react'
import { useRef } from 'react'
import { useSheetCover, useSheetTop } from '@/window/cover'

function rect(top: number): DOMRect {
  return { top, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: top, toJSON: () => ({}) } as DOMRect
}

function Sheet({ shown }: { shown: boolean }) {
  const sheet = useRef<HTMLElement>(null)
  useSheetCover(sheet, shown)
  return <aside ref={sheet} aria-label="Sheet" />
}

afterEach(() => useSheetTop.setState({ sheetTop: null }))

it('publishes the top the sheet takes and keeps none once the sheet is gone', () => {
  const measured = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(rect(300))
  try {
    const view = render(<Sheet shown={false} />)
    expect(useSheetTop.getState().sheetTop).toBeNull()
    view.rerender(<Sheet shown />)
    expect(useSheetTop.getState().sheetTop).toBe(300)
    view.rerender(<Sheet shown={false} />)
    expect(useSheetTop.getState().sheetTop).toBeNull()
  } finally {
    measured.mockRestore()
  }
})
