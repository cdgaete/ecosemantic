import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { rememberToken } from '@/api/client'
import { useHeldStream } from '@/api/stream'
import { BackgroundEditor } from '@/editors/background/BackgroundEditor'
import { SearchEditor } from '@/editors/background/SearchEditor'
import { DatabasesEditor } from '@/editors/databases/DatabasesEditor'
import { NoEditor } from '@/editors/NoEditor'
import { ProcessEditor } from '@/editors/process/ProcessEditor'
import { ResultsEditor } from '@/editors/results/ResultsEditor'
import { SimulationEditor } from '@/editors/simulation/SimulationEditor'
import { SystemEditor, VersionEditor } from '@/editors/system/SystemEditor'
import { Welcome } from '@/editors/Welcome'
import { RequestDialog } from '@/requests/RequestDialog'
import { Toaster } from 'sonner'
import { Window } from '@/window/Window'
import { TooltipProvider } from '@/components/ui/tooltip'

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

function TokenKeeper() {
  const location = useLocation()
  useEffect(() => {
    rememberToken(location.search)
  }, [location.search])
  return null
}

export function Screens() {
  return (
    <TooltipProvider>
      <TokenKeeper />
      <Routes>
        <Route element={<Window />}>
          <Route index element={<Welcome />} />
          <Route path="systems/:id/versions/:hash/*" element={<VersionEditor />} />
          <Route path="systems/:id/processes/:code/*" element={<ProcessEditor />} />
          <Route path="systems/:id/results/*" element={<ResultsEditor />} />
          <Route path="databases" element={<DatabasesEditor />} />
          <Route path="databases/:name/processes/:ref" element={<BackgroundEditor />} />
          <Route path="databases/:name/search/:kind" element={<SearchEditor />} />
          <Route path="systems/:id/simulations/:runId" element={<SimulationEditor />} />
          <Route path="systems/:id/*" element={<SystemEditor />} />
          <Route path="*" element={<NoEditor />} />
        </Route>
      </Routes>
      <RequestDialog />
      <Toaster />
    </TooltipProvider>
  )
}

function HeldStream() {
  useHeldStream()
  return null
}

export function App({ router = true }: { router?: boolean }) {
  const screens = <Screens />
  return (
    <QueryClientProvider client={client}>
      <HeldStream />
      {router ? <BrowserRouter>{screens}</BrowserRouter> : screens}
    </QueryClientProvider>
  )
}
