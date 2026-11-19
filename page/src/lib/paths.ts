import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { withToken } from '@/api/client'

export function useGo() {
  const navigate = useNavigate()
  return useCallback((path: string) => navigate(withToken(path)), [navigate])
}

export type ExplorerSection = 'datasets' | 'flows' | 'methods' | 'units' | 'locations'

export type SearchKind = 'processes' | 'elementary-flows' | 'methods'

export const paths = {
  home: () => '/',
  system: (id: string) => `/systems/${id}`,
  systemPage: (id: string, page: string) => `/systems/${id}/${page}`,
  version: (id: string, hash: string) => `/systems/${id}/versions/${hash}`,
  process: (id: string, code: string, page = 'general') => `/systems/${id}/processes/${code}/${page}`,
  resultList: (id: string) => `/systems/${id}/results`,
  results: (id: string, page: string, search: string) => `/systems/${id}/results/${page}${search}`,
  simulation: (id: string, runId: string) => `/systems/${id}/simulations/${runId}`,
  background: (database: string, ref: string) => `/databases/${database}/processes/${ref}`,
  dataset: (id: string, database: string, ref: string) => `/systems/${id}/datasets/${database}/${ref}`,
  explorer: (database: string, section: ExplorerSection = 'datasets', search = '') => `/databases/${database}/${section}${search}`,
  flow: (database: string, ref: string) => `/databases/${database}/flows/${ref}`,
  indicator: (database: string, id: string) => `/databases/${database}/methods/${id}`,
  search: (database: string, kind: SearchKind = 'processes') => `/databases/${database}/search/${kind}`,
  databases: () => '/databases',
  accounts: () => '/accounts',
}

const DATABASE_ADDRESS = /^\/databases\/([^/]+)(?:\/|$)/

export function databaseOfPath(pathname: string): string | null {
  const found = DATABASE_ADDRESS.exec(pathname)
  return found === null ? null : decodeURIComponent(found[1])
}

export function isActivityPath(pathname: string, id: string): boolean {
  const base = paths.system(id)
  return pathname === base || pathname === `${base}/` || pathname === `${base}/log` || pathname === `${base}/graph`
}
