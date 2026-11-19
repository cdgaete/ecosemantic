import { Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { withToken } from '@/api/client'
import { useAddress } from '@/lib/address'
import { paths, type ExplorerSection } from '@/lib/paths'
import { usePausedDraft } from './usePausedDraft'
import { SEARCHED, searchedFrom, TITLES } from './sections'

const KEPT = ['scheme', 'location', 'unit', 'compartment_filter']

/** The whole-database search of one database: its text, and whether it reads datasets, elementary flows or impact methods. */
export function DatabaseSearch({ name, section }: { name: string; section: ExplorerSection }) {
  const address = useAddress()
  const navigate = useNavigate()
  const whole = address.read('whole') === '1'
  const target = searchedFrom(section)
  const searching = whole && target === section
  const search = (into: ExplorerSection, text: string) => {
    const asked = new URLSearchParams({ whole: '1' })
    if (text !== '') asked.set('q', text)
    if (searching && into === section) {
      for (const key of KEPT) {
        const held = address.read(key)
        if (held !== '') asked.set(key, held)
      }
    }
    navigate(withToken(`${paths.explorer(name, into)}?${asked.toString()}`), { replace: searching && into === section })
  }
  const { draft, type, settle } = usePausedDraft(searching ? address.read('q') : '', (text) => search(target, text))
  return (
    <form
      role="search"
      aria-label={`Search ${name}`}
      className="ml-auto flex min-w-0 max-w-full flex-wrap items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault()
        search(target, settle())
      }}
    >
      <label htmlFor="explorer-search" className="sr-only">
        Search the database
      </label>
      <span className="relative flex min-w-0 items-center">
        <Search aria-hidden className="pointer-events-none absolute left-2 size-3.5 text-muted-foreground" />
        <input
          id="explorer-search"
          type="search"
          className="w-64 min-w-0 max-w-full rounded-md border bg-background py-1 pr-2 pl-7 text-xs"
          placeholder={`Search ${TITLES[target].toLowerCase()}…`}
          value={draft}
          onChange={(event) => type(event.target.value)}
        />
      </span>
      <label className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
        in
        <select
          aria-label="Search in"
          className="min-w-0 max-w-full rounded-sm border bg-background px-1 py-0.5 text-xs text-foreground"
          value={target}
          onChange={(event) => search(event.target.value as ExplorerSection, settle())}
        >
          {SEARCHED.map((entry) => (
            <option key={entry} value={entry}>
              {TITLES[entry]}
            </option>
          ))}
        </select>
      </label>
    </form>
  )
}
