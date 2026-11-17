import { fireEvent, screen } from '@testing-library/react'
import { MenuButton, MenuStrip } from '@/window/MenuBar'
import { menus } from '@/window/menus'
import { renderAt } from './render'

const nothing = (): void => undefined

const all = menus({
  systemId: null,
  resultOpen: false,
  openRequests: 0,
  theme: 'light',
  inspector: 'open',
  inspectorShown: true,
  openInspector: nothing,
  closeInspector: nothing,
  toggleWidened: nothing,
  openNavigation: nothing,
  importFile: nothing,
  downloadResult: nothing,
  setTheme: nothing,
  newRequest: nothing,
  reorganise: nothing,
  resetLayout: nothing,
})

const go = nothing

describe('menu bar', () => {
  it('lists the four menus in the strip', () => {
    renderAt('/', <MenuStrip menus={all} go={go} />)
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['File', 'Calculate', 'View', 'Requests'])
  })

  it('holds the four menus behind one button in the dock', () => {
    renderAt('/', <MenuButton menus={all} go={go} />)
    fireEvent.keyDown(screen.getByRole('button', { name: 'Menus' }), { key: 'Enter' })
    for (const label of ['File', 'Calculate', 'View', 'Requests']) expect(screen.getByText(label)).toBeInTheDocument()
  })
})
