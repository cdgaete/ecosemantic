import { act, fireEvent, render, screen } from '@testing-library/react'
import { ListingFilter } from '@/editors/explorer/ListingControls'
import { FILTER_PAUSE_MS } from '@/editors/explorer/usePausedDraft'

const TYPED = 'methane, fossil'

function renderFilter(onChange: (value: string) => void, value = '') {
  return render(<ListingFilter id="probe-filter" label="Filter the probe" value={value} onChange={onChange} />)
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

it('shows each character at once and calls onChange once, a pause after the last one', () => {
  const onChange = vi.fn()
  renderFilter(onChange)
  const input = screen.getByLabelText('Filter the probe')
  for (let end = 1; end <= TYPED.length; end += 1) {
    fireEvent.change(input, { target: { value: TYPED.slice(0, end) } })
    expect(input).toHaveValue(TYPED.slice(0, end))
    expect(onChange).not.toHaveBeenCalled()
  }
  act(() => vi.advanceTimersByTime(FILTER_PAUSE_MS - 1))
  expect(onChange).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(1))
  expect(onChange).toHaveBeenCalledTimes(1)
  expect(onChange).toHaveBeenCalledWith(TYPED)
})

it('takes a value written from outside over a waiting draft and sends nothing', () => {
  const onChange = vi.fn()
  const view = renderFilter(onChange)
  fireEvent.change(screen.getByLabelText('Filter the probe'), { target: { value: 'meth' } })
  view.rerender(<ListingFilter id="probe-filter" label="Filter the probe" value="steel" onChange={onChange} />)
  expect(screen.getByLabelText('Filter the probe')).toHaveValue('steel')
  act(() => vi.advanceTimersByTime(FILTER_PAUSE_MS * 2))
  expect(onChange).not.toHaveBeenCalled()
})

it('keeps the characters typed after the draft came back as the value', () => {
  const onChange = vi.fn()
  const view = renderFilter(onChange)
  const input = screen.getByLabelText('Filter the probe')
  fireEvent.change(input, { target: { value: 'm' } })
  act(() => vi.advanceTimersByTime(FILTER_PAUSE_MS))
  expect(onChange).toHaveBeenCalledWith('m')
  view.rerender(<ListingFilter id="probe-filter" label="Filter the probe" value="m" onChange={onChange} />)
  fireEvent.change(input, { target: { value: 'me' } })
  fireEvent.change(input, { target: { value: 'met' } })
  expect(input).toHaveValue('met')
  act(() => vi.advanceTimersByTime(FILTER_PAUSE_MS))
  expect(onChange).toHaveBeenCalledTimes(2)
  expect(onChange).toHaveBeenLastCalledWith('met')
})

it('sends nothing when it unmounts with a draft waiting', () => {
  const onChange = vi.fn()
  const view = renderFilter(onChange)
  fireEvent.change(screen.getByLabelText('Filter the probe'), { target: { value: 'methane' } })
  view.unmount()
  act(() => vi.advanceTimersByTime(FILTER_PAUSE_MS * 2))
  expect(onChange).not.toHaveBeenCalled()
})
