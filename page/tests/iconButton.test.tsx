import { fireEvent, render, screen } from '@testing-library/react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { IconButton } from '@/window/IconButton'

function show(ui: React.ReactNode) {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

describe('icon button', () => {
  it('carries its label as its name and runs on a click', () => {
    const run = vi.fn()
    show(
      <IconButton label="Pin" onClick={run}>
        <svg />
      </IconButton>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Pin' }))
    expect(run).toHaveBeenCalledOnce()
  })

  it('says its label and the keys of its shortcut when it takes the focus', async () => {
    show(
      <IconButton label="Collapse panel" shortcut="panel" onClick={() => undefined}>
        <svg />
      </IconButton>,
    )
    fireEvent.focus(screen.getByRole('button', { name: 'Collapse panel' }))
    const tip = await screen.findByRole('tooltip')
    expect(tip).toHaveTextContent('Collapse panel')
    expect(tip).toHaveTextContent('Ctrl+Alt+B')
  })

  it('states whether it is pressed when it is a toggle', () => {
    show(
      <IconButton label="Hide navigation" pressed onClick={() => undefined}>
        <svg />
      </IconButton>,
    )
    expect(screen.getByRole('button', { name: 'Hide navigation' })).toHaveAttribute('aria-pressed', 'true')
  })
})
