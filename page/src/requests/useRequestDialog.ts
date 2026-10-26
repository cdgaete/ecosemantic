import { create } from 'zustand'
import type { Entity } from '@/api/types'

export interface RequestTarget {
  systemId: string
  entity?: Entity
  entityId?: string
}

interface RequestDialogState {
  target: RequestTarget | null
  open: (target: RequestTarget) => void
  close: () => void
}

export const useRequestDialog = create<RequestDialogState>()((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}))
