import { screen } from '@testing-library/react'
import { renderAt } from './render'
import { MenuBar } from '@/window/MenuBar'

describe('menu bar', () => {
  afterEach(() => {
    window.innerWidth = 1024
  })

  it('is four menus from 1024 px', () => {
    window.innerWidth = 1024
    renderAt('/', <MenuBar />)
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['File', 'Calculate', 'View', 'Requests'])
  })

  it('is one button below it', () => {
    window.innerWidth = 800
    renderAt('/', <MenuBar />)
    expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument()
    expect(screen.queryByText('Calculate')).not.toBeInTheDocument()
  })
})
