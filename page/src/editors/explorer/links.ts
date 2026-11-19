import { paths } from '@/lib/paths'

export interface DatasetLinks {
  process: (database: string, ref: string) => string
  flow: (database: string, ref: string) => string
}

export const EXPLORER_LINKS: DatasetLinks = { process: paths.background, flow: paths.flow }

/** The links of a dataset shown beside a system's graph: a supplier opens beside the graph too, and a flow in the explorer. */
export function besideGraph(systemId: string): DatasetLinks {
  return { process: (database, ref) => paths.dataset(systemId, database, ref), flow: paths.flow }
}
