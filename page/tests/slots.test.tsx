import { render, screen } from '@testing-library/react'
import { InSlot, Slot, SlotsProvider } from '@/window/slots'

describe('slots', () => {
  it('draws what a slot is given where the slot is', () => {
    const view = render(
      <SlotsProvider>
        <div data-testid="frame">
          <Slot name="tools" />
        </div>
        <InSlot name="tools">
          <p>the canvas toolbar</p>
        </InSlot>
      </SlotsProvider>,
    )
    expect(view.getByTestId('frame').querySelector('p')?.textContent).toBe('the canvas toolbar')
  })

  it('draws nothing for a slot the frame does not hold', () => {
    const view = render(
      <SlotsProvider>
        <Slot name="minimap" />
        <InSlot name="notice">
          <p>read-only</p>
        </InSlot>
      </SlotsProvider>,
    )
    expect(screen.queryByText('read-only')).not.toBeInTheDocument()
    expect(view.container.querySelector('p')).toBeNull()
  })
})
