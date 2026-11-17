import { useUi, type InspectorMode } from '@/store/ui'
import { inspectorShown, openInspector, opensInspector, toggleInspector, toggleWidened } from '@/window/inspector'

describe('inspectorShown', () => {
  it.each([
    [{ inspector: 'closed', sheetOpen: true }, false, false],
    [{ inspector: 'open', sheetOpen: false }, true, false],
    [{ inspector: 'closed', sheetOpen: true }, true, true],
    [{ inspector: 'widened', sheetOpen: false }, false, true],
  ] as [{ inspector: InspectorMode; sheetOpen: boolean }, boolean, boolean][])('answers %o at %s narrow as %s', (state, narrow, shown) => {
    expect(inspectorShown(state, narrow)).toBe(shown)
  })
})

describe('the inspector', () => {
  beforeEach(() => {
    useUi.setState({ inspector: 'open', sheetOpen: false })
  })

  afterEach(() => {
    window.innerWidth = 1024
    useUi.setState({ inspector: 'open', sheetOpen: false })
  })

  it('shows and hides the inspector from 768 px and keeps the sheet as it is', () => {
    window.innerWidth = 1024
    toggleInspector()
    expect(useUi.getState().inspector).toBe('closed')
    expect(useUi.getState().sheetOpen).toBe(false)
    toggleInspector()
    expect(useUi.getState().inspector).toBe('open')
    expect(useUi.getState().sheetOpen).toBe(false)
  })

  it('shows and hides the sheet below 768 px and keeps the inspector as it is', () => {
    window.innerWidth = 700
    useUi.setState({ inspector: 'closed' })
    toggleInspector()
    expect(useUi.getState().sheetOpen).toBe(true)
    expect(useUi.getState().inspector).toBe('closed')
    toggleInspector()
    expect(useUi.getState().sheetOpen).toBe(false)
    expect(useUi.getState().inspector).toBe('closed')
  })

  it('keeps a widened inspector widened when it is opened', () => {
    useUi.setState({ inspector: 'widened' })
    openInspector()
    expect(useUi.getState().inspector).toBe('widened')
  })

  it('opens a closed inspector widened when widened', () => {
    useUi.setState({ inspector: 'closed' })
    toggleWidened()
    expect(useUi.getState().inspector).toBe('widened')
    toggleWidened()
    expect(useUi.getState().inspector).toBe('open')
  })

  it('opens the inspector for a page of a system and not for its Activity', () => {
    expect(opensInspector('/systems/s1/general')).toBe(true)
    expect(opensInspector('/systems/s1/processes/p1/io')).toBe(true)
    expect(opensInspector('/systems/s1')).toBe(false)
    expect(opensInspector('/systems/s1/log')).toBe(false)
    expect(opensInspector('/databases')).toBe(false)
    expect(opensInspector('/')).toBe(false)
  })
})
