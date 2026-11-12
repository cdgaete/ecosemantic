import type { Credential } from '@/api/types'

export type AccountInput = { username: string; password: string; token: string }

export function entered(value: AccountInput): Credential {
  return { username: value.username, password: value.password, token: value.token === '' ? undefined : value.token }
}
