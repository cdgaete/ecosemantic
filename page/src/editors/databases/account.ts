import type { Credential, CredentialKind } from '@/api/types'

export type AccountInput = { username: string; password: string; token: string }

export const ACCOUNT_NAMES: Record<CredentialKind, { name: string; phrase: string }> = {
  ecoinvent: { name: 'ecoinvent', phrase: 'an ecoinvent account' },
  nexus: { name: 'Nexus', phrase: 'a Nexus account' },
}

export function entered(value: AccountInput): Credential {
  return { username: value.username, password: value.password, token: value.token === '' ? undefined : value.token }
}
