import { settled } from '@/window/tools'

// the toolbar docked at the top centre of a 1440 x 900 page: 400 px wide, 38 px high
const DOCKED = { left: 520, top: 12, right: 920, bottom: 50 }
// the clear area under a name island 98 px high, beside a dock, an inspector 400 px wide and a timeline
const AREA = { x: 68, y: 110, width: 948, height: 650 }

describe('where the canvas tools settle', () => {
  it('keeps the place they are dropped at inside the clear area', () => {
    expect(settled(DOCKED, { x: -100, y: 300 }, AREA)).toEqual({ x: -100, y: 300 })
  })

  it('holds them inside the left, the right and the bottom of the clear area', () => {
    // the left edge of the area is 68: 68 - 520
    expect(settled(DOCKED, { x: -1000, y: 300 }, AREA)).toEqual({ x: -452, y: 300 })
    // the area ends at 1016 and the toolbar is 400 wide: 616 - 520
    expect(settled(DOCKED, { x: 1000, y: 300 }, AREA)).toEqual({ x: 96, y: 300 })
    // the area ends at 760 and the toolbar is 38 high: 722 - 12
    expect(settled(DOCKED, { x: 0, y: 2000 }, AREA)).toEqual({ x: 0, y: 710 })
  })

  it('returns them to the top centre when they are dropped above the clear area', () => {
    expect(settled(DOCKED, { x: 200, y: 40 }, AREA)).toBeNull()
    expect(settled(DOCKED, { x: 0, y: 0 }, AREA)).toBeNull()
    // 12 + 98 is the top of the area
    expect(settled(DOCKED, { x: 0, y: 98 }, AREA)).toEqual({ x: 0, y: 98 })
  })

  it('starts them at the left of a clear area narrower than they are', () => {
    expect(settled(DOCKED, { x: 0, y: 300 }, { ...AREA, width: 300 })).toEqual({ x: -452, y: 300 })
  })
})
