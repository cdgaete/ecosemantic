import { useState, type ReactNode } from 'react'
import { ApiError, api } from '@/api/client'
import { usePostInstall, usePutCredential, useUploadDatabase } from '@/api/queries'
import type { DatabaseSource, Install, InstallDraft } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const SELECT = 'h-8 w-full min-w-0 rounded-md border bg-background px-2 text-sm'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

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
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [accepted, setAccepted] = useState(false)
  const put = usePutCredential()
  const post = usePostInstall()
  const upload = useUploadDatabase()
  const account = source.credential !== null && !source.held ? source.credential : null
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
  const entered = { username, password, token: token === '' ? undefined : token }
  const send = () => {
    if (account === null) post.mutate(draft(accepted))
    else put.mutate({ kind: account, account: entered }, { onSuccess: () => post.mutate(draft(accepted)) })
  }
  const add = () => {
    if (account === null) return
    put.mutate({ kind: account, account: entered })
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
          {account === null ? null : (
            <>
              <Field label="Username">
                <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
              </Field>
              <Field label="Password">
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" />
              </Field>
              {account === 'nexus' ? (
                <Field label="Token">
                  <Input value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
                </Field>
              ) : null}
            </>
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
            {account === null ? null : (
              <Button size="sm" variant="outline" onClick={add}>
                Add credentials
              </Button>
            )}
            <Button size="sm" disabled={quoted !== null && !accepted} onClick={send}>
              Install
            </Button>
          </div>
        </>
      )}
      <Refusal error={put.error ?? post.error ?? upload.error} />
    </div>
  )
}
