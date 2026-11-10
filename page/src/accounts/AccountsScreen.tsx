import { useEffect, useState } from 'react'
import logo from '@/assets/logo.svg'
import { useAccountEntry, useCredentials, useDeleteCredential, usePutCredential, useSources } from '@/api/queries'
import type { CredentialKind, DatabaseSource } from '@/api/types'
import { Button } from '@/components/ui/button'
import { AccountAdvice, KEPT } from '@/editors/databases/AccountAdvice'
import { AccountFields } from '@/editors/databases/AccountFields'
import { ACCOUNT_NAMES, entered, type AccountInput } from '@/editors/databases/account'

const TITLE = 'Database accounts — EcoSemantic'
const NOT_SAVED = 'Not saved'
const SAVED = 'Saved until EcoSemantic restarts'

function needed(sources: DatabaseSource[]): { kind: CredentialKind; names: string[] }[] {
  const kinds = new Map<CredentialKind, string[]>()
  for (const source of sources) {
    if (source.credential === null) continue
    kinds.set(source.credential, [...(kinds.get(source.credential) ?? []), source.name])
  }
  return [...kinds].map(([kind, names]) => ({ kind, names }))
}

function Card({
  kind,
  names,
  page,
  held,
  here,
}: {
  kind: CredentialKind
  names: string[]
  page: string | null
  held: boolean
  here: boolean
}) {
  const [account, setAccount] = useState<AccountInput>({ username: '', password: '', token: '' })
  const put = usePutCredential()
  const remove = useDeleteCredential()
  const refusal = put.error ?? remove.error
  return (
    <section aria-label={ACCOUNT_NAMES[kind].name} className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-3">
      <h2 className="text-sm font-semibold break-words">{ACCOUNT_NAMES[kind].name}</h2>
      <p className="text-xs text-muted-foreground">Opens {names.join(' and ')}.</p>
      {here ? <p className="text-xs">{held ? SAVED : NOT_SAVED}</p> : null}
      <AccountFields kind={kind} value={account} onChange={setAccount} disabled={!here} />
      {here ? <p className="text-xs text-muted-foreground">{KEPT}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!here} onClick={() => put.mutate({ kind, account: entered(account) })}>
          Save
        </Button>
        <Button size="sm" variant="outline" disabled={!here || !held} onClick={() => remove.mutate(kind)}>
          Remove
        </Button>
      </div>
      {refusal === null ? null : <p className="text-xs break-words text-destructive">{refusal.message}</p>}
      {put.isSuccess ? (
        <p className="text-xs break-words text-muted-foreground">
          Saved. Go back to the chat and ask again
          {page === null ? (
            '.'
          ) : (
            <>
              , or continue on{' '}
              <a href={page} className="text-primary hover:underline">
                your page
              </a>
              .
            </>
          )}
        </p>
      ) : null}
    </section>
  )
}

export function AccountsScreen() {
  const entry = useAccountEntry()
  const sources = useSources()
  const here = entry.data?.here === true
  const credentials = useCredentials(here)
  const held = credentials.data?.held ?? []
  const cards = needed(sources.data?.value ?? []).map(({ kind, names }) => (
    <Card
      key={kind}
      kind={kind}
      names={names}
      page={entry.data?.page ?? null}
      held={held.includes(kind)}
      here={here}
    />
  ))
  const advice = entry.data !== undefined && !here ? entry.data : null
  useEffect(() => {
    document.title = TITLE
  }, [])
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col gap-4 p-6 text-sm leading-snug">
      <header className="flex flex-col gap-1">
        <span className="flex items-center gap-2">
          <img src={logo} alt="EcoSemantic" className="size-6 shrink-0" />
          <h1 className="text-base font-semibold">Database accounts</h1>
        </span>
        <p className="text-xs text-muted-foreground">on this computer</p>
      </header>
      {entry.error ? <p className="break-words text-destructive">{entry.error.message}</p> : null}
      {sources.error ? <p className="break-words text-destructive">{sources.error.message}</p> : null}
      {advice === null ? (
        <div className="flex flex-col gap-3">{cards}</div>
      ) : (
        <AccountAdvice entry={advice}>
          <div className="flex flex-col gap-3">{cards}</div>
        </AccountAdvice>
      )}
    </main>
  )
}
