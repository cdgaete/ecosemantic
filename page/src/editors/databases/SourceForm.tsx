import { useState } from 'react'
import { ApiError, api } from '@/api/client'
import { useAccountEntry, usePostInstall, usePutCredential, useUploadDatabase } from '@/api/queries'
import type { DatabaseSource, Install, InstallDraft } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AccountAdvice, KEPT } from './AccountAdvice'
import { AccountFields } from './AccountFields'
import { entered, type AccountInput } from './account'
import { Field } from './Field'

const SELECT = 'h-8 w-full min-w-0 rounded-md border bg-background px-2 text-sm'

function Refusal({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return null
  const hint = error.details.hint
  return (
    <div role="alert" className="flex flex-col gap-0.5 text-xs">
      <p className="text-destructive">{error.message}</p>
      {typeof hint === 'string' ? <p className="text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

export function SourceForm({ source, terms }: { source: DatabaseSource; terms: Install | null }) {
  const [version, setVersion] = useState(source.versions[0] ?? '')
  const [model, setModel] = useState(source.system_models[0] ?? '')
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [account, setAccount] = useState<AccountInput>({ username: '', password: '', token: '' })
  const [accepted, setAccepted] = useState(false)
  const put = usePutCredential()
  const post = usePostInstall()
  const upload = useUploadDatabase()
  const entry = useAccountEntry()
  const here = entry.data?.here === true
  const advice = entry.data !== undefined && !here ? entry.data : null
  const kind = source.credential !== null && !source.held ? source.credential : null
  const quoted = terms?.terms ?? null
  const licence = terms === null ? null : api.licenceUrl(terms.id)
  const draft = (accept: boolean): Omit<InstallDraft, 'actor'> => ({
    source: source.name,
    version: version === '' ? null : version,
    system_model: model === '' ? null : model,
    replace: false,
    accept_terms: accept,
    package: null,
    name: null,
    drop_unlinked: false,
  })
  const blocked = kind !== null && !here
  const send = () => {
    if (kind === null) post.mutate(draft(accepted))
    else put.mutate({ kind, account: entered(account) }, { onSuccess: () => post.mutate(draft(accepted)) })
  }
  const add = () => {
    if (kind === null) return
    put.mutate({ kind, account: entered(account) })
  }
  const transfer = () => {
    if (file === null) return
    const form = new FormData()
    form.set('file', file)
    form.set('name', name)
    form.set('version', version)
    upload.mutate(form)
  }
  return (
    <div className="flex max-w-md flex-col gap-2 pt-3 text-xs">
      {source.name === 'openlca' ? (
        <>
          <Field label="The zip you hold">
            <input type="file" accept=".zip" className="text-xs" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Version">
            <Input value={version} onChange={(e) => setVersion(e.target.value)} />
          </Field>
          <div>
            <Button size="sm" disabled={file === null || name === '' || version === ''} onClick={transfer}>
              Upload
            </Button>
          </div>
        </>
      ) : (
        <>
          {source.versions.length > 0 ? (
            <Field label="Version">
              <select className={SELECT} value={version} onChange={(e) => setVersion(e.target.value)}>
                {source.versions.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          {source.system_models.length > 0 ? (
            <Field label="System model">
              <select className={SELECT} value={model} onChange={(e) => setModel(e.target.value)}>
                {source.system_models.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          {kind === null ? null : advice === null ? (
            <>
              <AccountFields kind={kind} value={account} onChange={setAccount} disabled={!here} />
              {here ? <p className="text-muted-foreground">{KEPT}</p> : null}
            </>
          ) : (
            <AccountAdvice entry={advice}>
              <AccountFields kind={kind} value={account} onChange={setAccount} disabled />
            </AccountAdvice>
          )}
          {quoted === null || licence === null ? null : (
            <div className="flex flex-col gap-1.5 rounded-md border bg-background px-2 py-1.5">
              <p className="break-words">{quoted.citation}</p>
              <a href={licence} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                Read the terms
              </a>
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />I accept the terms
              </label>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {kind === null ? null : (
              <Button size="sm" variant="outline" disabled={blocked} onClick={add}>
                Add credentials
              </Button>
            )}
            <Button size="sm" disabled={blocked || (quoted !== null && !accepted)} onClick={send}>
              Install
            </Button>
          </div>
        </>
      )}
      <Refusal error={entry.error ?? put.error ?? post.error ?? upload.error} />
    </div>
  )
}
