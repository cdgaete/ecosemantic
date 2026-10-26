import { render, waitFor } from '@testing-library/react'
import { Position, ReactFlow, ReactFlowProvider } from '@xyflow/react'
import { routePath } from '@/editors/graph/layout'
import { FlowEdge } from '@/editors/graph/FlowEdge'

function drawn(amount: number, points: [number, number][] | null = null, rest = false): SVGPathElement {
  const props = { id: 'e', source: 'a', target: 'b', sourceX: 0, sourceY: 3, targetX: 100, targetY: 3, sourcePosition: Position.Right, targetPosition: Position.Left, data: { amount, unit: 'kg', formula: null, points, rest } }
  const { container } = render(
    <ReactFlowProvider>
      <svg>
        <FlowEdge {...(props as unknown as Parameters<typeof FlowEdge>[0])} />
      </svg>
    </ReactFlowProvider>,
  )
  return container.querySelector('path.react-flow__edge-path') as SVGPathElement
}

it('dashes an arrow whose amount is zero and draws the others whole', () => {
  expect(drawn(0).style.strokeDasharray).not.toBe('')
  expect(drawn(2).style.strokeDasharray).toBe('')
})

it('draws the server route while the arrow is at rest, and the step path once it is not', () => {
  const route: [number, number][] = [[0, 0], [40, 0], [40, 20], [100, 20]]
  expect(drawn(1, route, true).getAttribute('d')).toBe(routePath(route))
  const step = drawn(1, route, false).getAttribute('d')
  expect(step).not.toBe(routePath(route))
  expect(step).toBe(drawn(1).getAttribute('d'))
  expect(drawn(1, null, true).getAttribute('d')).toBe(step)
})

function labelled(rest: boolean) {
  const handle = { width: 1, height: 1, x: 0, y: 0 }
  const nodes = [
    { id: 'a', position: { x: 0, y: 0 }, data: {}, width: 50, height: 20, handles: [{ ...handle, type: 'source' as const, position: Position.Right, id: 'out', x: 50 }] },
    { id: 'b', position: { x: 200, y: 0 }, data: {}, width: 50, height: 20, handles: [{ ...handle, type: 'target' as const, position: Position.Left, id: 'in' }] },
  ]
  const edges = [{ id: 'e', source: 'a', target: 'b', sourceHandle: 'out', targetHandle: 'in', type: 'flow', data: { amount: 1, unit: 'kg', formula: null, points: [[50, 0], [200, 0]], rest, label: { x: 12, y: 34, width: 90, height: 16, text: '1.25 kg' } } }]
  return render(
    <div style={{ width: 800, height: 400 }}>
      <ReactFlow nodes={nodes} edges={edges} edgeTypes={{ flow: FlowEdge }} />
    </div>,
  )
}

it('writes the label text in its server box while the arrow is at rest, and not once it is not', async () => {
  const view = labelled(true)
  const label = (await view.findByTestId('edge-label')) as HTMLElement
  expect(label.textContent).toBe('1.25 kg')
  expect(label.style.transform).toBe('translate(12px, 34px)')
  expect(label.style.width).toBe('90px')
  expect(label.style.height).toBe('16px')
  expect(label.className).toContain('text-right')
  expect(label.className).toContain('text-xs')
  view.unmount()
  const moving = labelled(false)
  await waitFor(() => expect(moving.container.querySelector('.react-flow__edge')).not.toBeNull())
  expect(moving.queryByTestId('edge-label')).toBeNull()
})
