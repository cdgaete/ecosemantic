import { useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queries'
import { paths, useGo } from '@/lib/paths'
import { useUi } from '@/store/ui'

/** Opens a result page as a calculation the person started: the impacts held for the system are dropped, so the page computes again and the server records it. */
export function useStartImpact(id: string): (page: string, search: string) => void {
  const go = useGo()
  const client = useQueryClient()
  return (page, search) => {
    useUi.getState().startImpact(id)
    client.removeQueries({ queryKey: keys.impacts(id) })
    go(paths.results(id, page, search))
  }
}
