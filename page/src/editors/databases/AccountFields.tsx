import type { CredentialKind } from '@/api/types'
import { Input } from '@/components/ui/input'
import type { AccountInput } from './account'
import { Field } from './Field'

export function AccountFields({
  kind,
  value,
  onChange,
  disabled,
}: {
  kind: CredentialKind
  value: AccountInput
  onChange: (value: AccountInput) => void
  disabled: boolean
}) {
  return (
    <>
      <Field label="Username">
        <Input
          value={value.username}
          onChange={(e) => onChange({ ...value, username: e.target.value })}
          autoComplete="off"
          disabled={disabled}
        />
      </Field>
      <Field label="Password">
        <Input
          type="password"
          value={value.password}
          onChange={(e) => onChange({ ...value, password: e.target.value })}
          autoComplete="off"
          disabled={disabled}
        />
      </Field>
      {kind === 'nexus' ? (
        <Field label="Token">
          <Input
            value={value.token}
            onChange={(e) => onChange({ ...value, token: e.target.value })}
            autoComplete="off"
            disabled={disabled}
          />
        </Field>
      ) : null}
    </>
  )
}
