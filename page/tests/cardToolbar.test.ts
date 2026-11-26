import { clearArea, toolbarFor } from '@/editors/graph/layout'

const CLEAR = { x: 12, y: 122, width: 676, height: 646 }
const NATURAL = { width: 425, height: 34 }
const CARD = { x: 412, y: 300, width: 200, height: 220 }

describe("the card toolbar's placement", () => {
  it('shifts the toolbar just enough to keep both ends inside the clear area', () => {
    const placed = toolbarFor({ card: CARD, natural: NATURAL, height: NATURAL.height, clear: CLEAR })
    expect(placed.left).toBe(263)
    expect(placed.left + NATURAL.width).toBe(688)
    expect(placed.width).toBeNull()
    expect(placed.side).toBe('top')
  })

  it('centres the toolbar on a card both of whose ends fit', () => {
    const placed = toolbarFor({ card: CARD, natural: { width: 300, height: 34 }, height: 34, clear: CLEAR })
    expect(placed.left).toBe(362)
  })

  it('holds the toolbar off the left edge of the clear area', () => {
    const placed = toolbarFor({ card: { ...CARD, x: 12, width: 100 }, natural: NATURAL, height: NATURAL.height, clear: CLEAR })
    expect(placed.left).toBe(12)
  })

  it('goes below the card when above it would cross the top of the clear area', () => {
    const card = (y: number) => ({ ...CARD, y })
    // a 34 px toolbar with an 8 px offset needs the card's top at 164 to clear 122
    expect(toolbarFor({ card: card(163), natural: NATURAL, height: 34, clear: CLEAR }).side).toBe('bottom')
    expect(toolbarFor({ card: card(164), natural: NATURAL, height: 34, clear: CLEAR }).side).toBe('top')
  })

  it('decides the side from the height the toolbar takes where it is drawn', () => {
    // the card's top is 50 px below the clear area's top: 34 px of one row clears it, 102 px of a wrapped row does not
    const card = { ...CARD, y: CLEAR.y + 50 }
    expect(toolbarFor({ card, natural: NATURAL, height: 34, clear: CLEAR }).side).toBe('top')
    expect(toolbarFor({ card, natural: NATURAL, height: 102, clear: CLEAR }).side).toBe('bottom')
  })

  it('narrows the toolbar to a clear area narrower than its row', () => {
    const placed = toolbarFor({ card: { ...CARD, x: 100 }, natural: NATURAL, height: 102, clear: { ...CLEAR, width: 300 } })
    expect(placed.width).toBe(300)
    expect(placed.left).toBe(12)
  })

  it('leaves the width to the content when the clear area holds its row in whole pixels', () => {
    // 424.219 px of content needs 425; a clear area of 425.4 px has room for them
    const placed = toolbarFor({ card: CARD, natural: { width: 424.219, height: 34 }, height: 34, clear: { ...CLEAR, width: 425.4 } })
    expect(placed.width).toBeNull()
  })

  it('gives a row that must wrap the whole pixels the clear area has', () => {
    const placed = toolbarFor({ card: CARD, natural: { width: 424.219, height: 102 }, height: 102, clear: { ...CLEAR, width: 300.7 } })
    expect(placed.width).toBe(300)
  })
})

describe("the card toolbar's pointer", () => {
  const wide = { width: 300, height: 34 }

  it('points at the centre of a card the toolbar is centred on', () => {
    const placed = toolbarFor({ card: CARD, natural: wide, height: wide.height, clear: CLEAR })
    expect(placed.left).toBe(362)
    expect(placed.pointer).toBe(150)
  })

  it('points at the card from a toolbar shifted off the left edge', () => {
    const placed = toolbarFor({ card: { ...CARD, x: 12, width: 100 }, natural: wide, height: wide.height, clear: CLEAR })
    expect(placed.left).toBe(12)
    expect(placed.pointer).toBe(50)
  })

  it('keeps the pointer inside the menu where the inspector pushes the toolbar left', () => {
    const placed = toolbarFor({ card: { ...CARD, x: 250 }, natural: wide, height: wide.height, clear: { ...CLEAR, width: 300 } })
    expect(placed.left).toBe(12)
    expect(placed.pointer).toBe(282)
  })

  it('points at the card from a toolbar placed below it', () => {
    const card = { ...CARD, y: CLEAR.y + 20 }
    const placed = toolbarFor({ card, natural: wide, height: wide.height, clear: CLEAR })
    expect(placed.side).toBe('bottom')
    expect(placed.pointer).toBe(150)
  })

  it('keeps the pointer inside a menu narrower than its card', () => {
    const placed = toolbarFor({ card: { ...CARD, x: 100 }, natural: NATURAL, height: 102, clear: { ...CLEAR, width: 120 } })
    expect(placed.width).toBe(120)
    expect(placed.left).toBe(12)
    expect(placed.pointer).toBe(102)
  })
})

describe('the clear area', () => {
  it('is the canvas less the clearance on each side', () => {
    expect(clearArea({ width: 1024, height: 768 }, { top: 122, right: 384, bottom: 132, left: 68 })).toEqual({ x: 68, y: 122, width: 572, height: 514 })
  })
})
