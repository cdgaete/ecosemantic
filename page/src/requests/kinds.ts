import type { Entity, RequestKind } from '@/api/types'

export interface KindWords {
  label: string
  named: boolean
  line: string
}

export const KIND_WORDS: Record<RequestKind, KindWords> = {
  return: {
    label: 'Return with an objection',
    named: false,
    line: 'The agent is asked to answer it, and it stays open until it is resolved.',
  },
  edit: {
    label: 'Ask for a change to',
    named: true,
    line: 'It stays open until it is resolved.',
  },
  approve: {
    label: 'Approve',
    named: false,
    line: 'Recorded beside the model: never counted, never open.',
  },
}

export function kindLabel(kind: RequestKind, entity?: Entity): string {
  const words = KIND_WORDS[kind]
  return words.named && entity !== undefined ? `${words.label} ${entity}` : words.label
}
