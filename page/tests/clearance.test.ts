import { clearanceOf, ISLAND_GAP, type Box } from '@/window/clearance'

const FRAME: Box = { left: 0, top: 0, right: 1048, bottom: 900 }

function box(left: number, top: number, right: number, bottom: number): Box {
  return { left, top, right, bottom }
}

describe('clearance', () => {
  it('clears each side by its farthest island and the gap', () => {
    expect(
      clearanceOf(FRAME, [
        { side: 'left', box: box(12, 12, 56, 300) },
        { side: 'top', box: box(68, 12, 500, 110) },
        { side: 'top', box: box(700, 12, 1036, 60) },
        { side: 'right', box: box(676, 72, 1036, 888) },
        { side: 'bottom', box: box(12, 780, 664, 888) },
      ]),
    ).toEqual({ left: 68, top: 122, right: 384, bottom: 132 })
  })

  it('counts an island of no size for nothing', () => {
    expect(clearanceOf(FRAME, [{ side: 'right', box: box(1048, 400, 1048, 400) }])).toEqual({ left: ISLAND_GAP, top: ISLAND_GAP, right: ISLAND_GAP, bottom: ISLAND_GAP })
  })

  it('leaves only the gap on a side with no island', () => {
    expect(clearanceOf(FRAME, [])).toEqual({ left: 12, top: 12, right: 12, bottom: 12 })
  })

  it('keeps the farthest of a bottom island and a minimap-sized one above it', () => {
    expect(
      clearanceOf(FRAME, [
        { side: 'bottom', box: box(12, 780, 664, 888) },
        { side: 'bottom', box: box(12, 640, 212, 790) },
      ]),
    ).toEqual({ left: 12, top: 12, right: 12, bottom: 272 })
  })

  it('counts a minimap that is closed for nothing', () => {
    expect(clearanceOf(FRAME, [{ side: 'bottom', box: box(12, 900, 12, 900) }])).toEqual({ left: ISLAND_GAP, top: ISLAND_GAP, right: ISLAND_GAP, bottom: ISLAND_GAP })
  })
})
