import type { Clearance } from '@/window/clearance'

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

export interface Bounds extends Size {
  x: number
  y: number
}

export interface Viewport {
  x: number
  y: number
  zoom: number
}

export interface ZoomLimits {
  min: number
  max: number
}

export interface Fit {
  target: Bounds
  anchor: Bounds | null
  canvas: Size
  clearance: Clearance
  zoom: ZoomLimits
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

export function clearArea(canvas: Size, clearance: Clearance): Bounds {
  return {
    x: clearance.left,
    y: clearance.top,
    width: canvas.width - clearance.left - clearance.right,
    height: canvas.height - clearance.top - clearance.bottom,
  }
}

export function clearCentre(canvas: Size, clearance: Clearance): Point {
  const area = clearArea(canvas, clearance)
  return { x: area.x + area.width / 2, y: area.y + area.height / 2 }
}

export type ToolbarSide = 'top' | 'bottom'

export const TOOLBAR_OFFSET = 8
export const POINTER_WIDTH = 10
export const POINTER_INSET = 18

export interface ToolbarPlacement {
  left: number
  width: number | null
  side: ToolbarSide
  pointer: number
}

export interface ToolbarFit {
  card: Bounds
  natural: Size
  height: number
  clear: Bounds
}

export function toolbarFor({ card, natural, height, clear }: ToolbarFit): ToolbarPlacement {
  const room = Math.floor(Math.max(clear.width, 0))
  const width = Math.ceil(natural.width) <= room ? null : room
  const span = width ?? natural.width
  const centre = card.x + card.width / 2
  const centred = centre - span / 2
  const left = Math.min(Math.max(centred, clear.x), clear.x + clear.width - span)
  const above = card.y - TOOLBAR_OFFSET - height
  const inset = Math.min(POINTER_INSET, span / 2)
  return {
    left,
    width,
    side: above >= clear.y ? 'top' : 'bottom',
    pointer: Math.min(Math.max(centre - left, inset), span - inset),
  }
}

export interface Reveal {
  box: Bounds
  viewport: Viewport
  clear: Bounds
}

/**
 * The viewport that moves just enough, at the zoom it holds, for `box` to sit inside `clear`; null when it already does,
 * when the region has no room, or when it cannot hold the box.
 */
export function revealFor({ box, viewport, clear }: Reveal): Viewport | null {
  if (clear.width <= 0 || clear.height <= 0) return null
  const width = box.width * viewport.zoom
  const height = box.height * viewport.zoom
  if (width > clear.width || height > clear.height) return null
  const left = viewport.x + box.x * viewport.zoom
  const top = viewport.y + box.y * viewport.zoom
  const x = left < clear.x ? clear.x - left : Math.min(clear.x + clear.width - width - left, 0)
  const y = top < clear.y ? clear.y - top : Math.min(clear.y + clear.height - height - top, 0)
  if (x === 0 && y === 0) return null
  return { x: viewport.x + x, y: viewport.y + y, zoom: viewport.zoom }
}

export function viewportFor({ target, anchor, canvas, clearance, zoom }: Fit): Viewport {
  const across = canvas.width - clearance.left - clearance.right
  const down = canvas.height - clearance.top - clearance.bottom
  const middle = clearCentre(canvas, clearance)
  const floor = Math.min(zoom.max, zoom.min)
  const whole = Math.min(zoom.max, across / target.width, down / target.height)
  if (whole >= floor) {
    return { x: middle.x - (target.x + target.width / 2) * whole, y: middle.y - (target.y + target.height / 2) * whole, zoom: whole }
  }
  if (anchor === null) {
    return { x: middle.x - (target.x + target.width / 2) * floor, y: middle.y - (target.y + target.height / 2) * floor, zoom: floor }
  }
  const row = target.height * floor <= down ? target.y + target.height / 2 : anchor.y + anchor.height / 2
  return { x: canvas.width - clearance.right - (anchor.x + anchor.width) * floor, y: middle.y - row * floor, zoom: floor }
}
