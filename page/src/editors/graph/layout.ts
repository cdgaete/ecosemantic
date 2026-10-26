export const READABLE_ZOOM = 0.5
export const FRAMED_ZOOM = 0.75
const FRAME_MARGIN = 1.4

export type Detail = 'rows' | 'header'

export interface Point {
  x: number
  y: number
}

export function routePath(points: [number, number][]): string {
  return points.map(([x, y], n) => `${n === 0 ? 'M' : 'L'} ${x} ${y}`).join(' ')
}

function sits(code: string, placed: ReadonlyMap<string, Point>, positions: ReadonlyMap<string, Point>): boolean {
  const spot = placed.get(code)
  const now = positions.get(code)
  return spot !== undefined && now !== undefined && spot.x === now.x && spot.y === now.y
}

export function atRest(source: string, target: string, placed: ReadonlyMap<string, Point>, positions: ReadonlyMap<string, Point>): boolean {
  return sits(source, placed, positions) && sits(target, placed, positions)
}

export function detailAt(zoom: number): Detail {
  return zoom >= READABLE_ZOOM ? 'rows' : 'header'
}

export interface Size {
  width: number
  height: number
}

export type Framing = 'suppliers' | 'changed' | 'whole'

function zoomFor(box: Size, view: Size): number {
  return Math.min(view.width / (box.width * FRAME_MARGIN), view.height / (box.height * FRAME_MARGIN))
}

export function framing(changed: Size, withSuppliers: Size, view: Size): Framing {
  if (view.width === 0 || view.height === 0) return 'changed'
  if (zoomFor(withSuppliers, view) >= FRAMED_ZOOM) return 'suppliers'
  if (zoomFor(changed, view) >= READABLE_ZOOM) return 'changed'
  return 'whole'
}
