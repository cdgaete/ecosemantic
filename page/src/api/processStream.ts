import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { followProcess } from './stream'

export function useProcessStream(): void {
  const client = useQueryClient()
  useEffect(() => followProcess(client), [client])
}
