import { render } from '@testing-library/react'
import { Icon } from '@/window/Icon'

it('renders a lucide icon with the role colour class', () => {
  const { container } = render(<Icon name="process" />)
  const svg = container.querySelector('svg')
  expect(svg).not.toBeNull()
  expect(svg?.getAttribute('class')).toContain('text-role-process')
})
