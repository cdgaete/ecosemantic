import { createContext, useContext, useEffect, useRef, useSyncExternalStore, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export type SlotName = 'tools' | 'view' | 'minimap' | 'notice'

interface Slots {
  hold: (name: SlotName, node: HTMLElement | null) => void
  held: (name: SlotName) => HTMLElement | null
  listen: (listener: () => void) => () => void
}

const SlotsContext = createContext<Slots | null>(null)

function emptySlots(): Slots {
  const held = new Map<SlotName, HTMLElement>()
  const listeners = new Set<() => void>()
  return {
    hold: (name, node) => {
      if (node === null) held.delete(name)
      else held.set(name, node)
      for (const listener of listeners) listener()
    },
    held: (name) => held.get(name) ?? null,
    listen: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}

function useSlots(): Slots {
  const slots = useContext(SlotsContext)
  if (slots === null) throw new Error('A slot needs the frame that holds it')
  return slots
}

export function SlotsProvider({ children }: { children: ReactNode }) {
  const [slots] = useState(emptySlots)
  return <SlotsContext.Provider value={slots}>{children}</SlotsContext.Provider>
}

export function Slot({ name, className }: { name: SlotName; className?: string }) {
  const slots = useSlots()
  const node = useRef<HTMLDivElement>(null)
  useEffect(() => {
    slots.hold(name, node.current)
    return () => slots.hold(name, null)
  }, [slots, name])
  return <div ref={node} className={className} />
}

export function InSlot({ name, children }: { name: SlotName; children: ReactNode }) {
  const slots = useSlots()
  const target = useSyncExternalStore(slots.listen, () => slots.held(name))
  return target === null ? null : createPortal(children, target)
}
