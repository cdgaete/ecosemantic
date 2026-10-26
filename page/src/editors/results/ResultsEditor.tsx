import { Route, Routes, useLocation } from 'react-router-dom'
import { useSystemStream } from '@/api/stream'
import { backwardsTreatmentNote, creditLoopNote, shortHash } from '@/lib/format'
import { paths, useGo } from '@/lib/paths'
import { PageTabs } from '@/window/PageTabs'
import { useEditorTab } from '@/window/useEditorTab'
import { CalculatePage } from './CalculatePage'
import { ContributionTreePage } from './ContributionTreePage'
import { GeneralPage } from './GeneralPage'
import { ImpactPage } from './ImpactPage'
import { InventoryPage } from './InventoryPage'
import { RESULT_PAGES } from './pages'
import { ProcessResultsPage } from './ProcessResultsPage'
import { ResultsList } from './ResultsList'
import { SankeyPage } from './SankeyPage'
import { useResult } from './useResult'

export function ResultsEditor() {
  const location = useLocation()
  if (/\/results\/?$/.test(location.pathname)) return <ResultsList />
  if (location.pathname.endsWith('/results/setup')) return <CalculatePage />
  return <OpenResult />
}

function OpenResult() {
  const result = useResult()
  const go = useGo()
  useSystemStream(result.id, go)
  const { resolved } = result
  if (resolved.error) return <p className="p-4 text-destructive">{resolved.error.message}</p>
  if (resolved.callId !== null && resolved.waiting) return <p className="p-4 text-muted-foreground">Loading…</p>
  if (resolved.callId !== null && result.call === null) return <p className="p-4 text-destructive">{`No calculation ${resolved.callId} is recorded for this product system.`}</p>
  if (result.params === null) return <CalculatePage />
  return <ResultPages result={result} />
}

function ResultPages({ result }: { result: Result }) {
  const location = useLocation()
  useEditorTab({ id: `results:${result.id}`, kind: 'results', title: `Results of: ${result.system?.name ?? ''}`, path: `${location.pathname}${location.search}` })
  const active = location.pathname.split('/results/')[1] ?? 'impact'
  const pages = RESULT_PAGES.map((p) => ({ ...p, path: paths.results(result.id, p.key, location.search) }))
  const scored = result.impact.data?.value
  const credits = scored
    ? [
        ...scored.credit_loops.map((codes) => creditLoopNote(codes)),
        ...scored.variants.flatMap((v) => v.credit_loops.map((codes) => creditLoopNote(codes, v.name))),
        ...scored.treatments_run_backwards.map((named) => backwardsTreatmentNote(named)),
        ...scored.variants.flatMap((v) => v.treatments_run_backwards.map((named) => backwardsTreatmentNote(named, v.name))),
      ]
    : []
  const recordedOn = result.call?.at_hash ?? null
  return (
    <div className="flex h-full flex-col">
      {recordedOn !== null && result.system && recordedOn !== result.system.hash ? (
        <div className="border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">
          {`Recorded on ${shortHash(recordedOn)}; computed here on the current model, ${shortHash(result.system.hash)}.`}
        </div>
      ) : null}
      {result.stale ? (
        <div className="flex items-center justify-between border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">
          The model changed since this result was computed.
          <button type="button" className="underline" onClick={result.recalculate}>
            Recalculate
          </button>
        </div>
      ) : null}
      {credits.length > 0 ? (
        <div className="border-b border-warning bg-warning/10 px-4 py-1 text-xs text-warning">
          {credits.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto pb-3">
        {result.impact.error ? <p className="p-4 text-destructive">{result.impact.error.message}</p> : null}
        <Routes>
          <Route path="general" element={<GeneralPage result={result} />} />
          <Route path="inventory" element={<InventoryPage result={result} />} />
          <Route path="impact" element={<ImpactPage result={result} />} />
          <Route path="processes" element={<ProcessResultsPage result={result} />} />
          <Route path="tree" element={<ContributionTreePage result={result} />} />
          <Route path="sankey" element={<SankeyPage result={result} />} />
        </Routes>
      </div>
      <PageTabs pages={pages} active={active} />
    </div>
  )
}

export type Result = ReturnType<typeof useResult>
