import { useLocation, useParams } from 'react-router-dom'
import { useBackgroundProcess } from '@/api/queries'
import { paths } from '@/lib/paths'
import { AppLink } from '@/lib/router'
import { EditorHeader } from '@/window/EditorHeader'
import { useEditorTab } from '@/window/useEditorTab'
import { besideGraph } from './links'
import { ProcessDetail } from './ProcessDetail'

function bare(): null {
  return null
}

/** One background process beside the graph of the system the address names, in Details, with the way to it in the explorer. */
export function DatasetPeek() {
  const params = useParams()
  const id = params.id ?? ''
  const database = params.database ?? ''
  const ref = params['*'] ?? ''
  const location = useLocation()
  const name = useBackgroundProcess(database, ref).data?.value.name ?? ''
  useEditorTab({ id: `dataset:${database}:${ref}`, kind: 'explorer', title: `Dataset: ${name}`, path: location.pathname })
  return (
    <>
      <EditorHeader icon="product" page="Dataset" entity={name} />
      <div className="flex min-w-0 flex-col px-4 pb-3">
        <AppLink to={paths.background(database, ref)} className="self-start text-xs text-accent hover:underline">
          Open in the explorer
        </AppLink>
        <ProcessDetail key={ref} name={database} item={ref} links={besideGraph(id)} header={bare} />
      </div>
    </>
  )
}
