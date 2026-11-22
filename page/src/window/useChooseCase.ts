import { useMatch } from 'react-router-dom'
import { useAddress } from '@/lib/address'
import { useUi } from '@/store/ui'

/**
 * Chooses the case or the scenario the canvas holds, and writes it into the address of an open
 * result so that every page of the result reads under it.
 */
export function useChooseCase(systemId: string): (name: string | null) => void {
  const setCanvasVariant = useUi((s) => s.setCanvasVariant)
  const address = useAddress()
  const matched = useMatch('/systems/:id/results/:page')
  const atResult = matched?.params.id === systemId
  return (name) => {
    setCanvasVariant(name)
    if (atResult) address.write({ variant: name ?? undefined })
  }
}
