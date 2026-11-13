import type { Method, Score } from '@/api/types'
import { methodById } from '@/lib/format'

export function firstMethodOf(value: { methods: Method[]; scores: Score[] }): Method {
  return methodById(value.methods, value.scores[0].method_id)
}
