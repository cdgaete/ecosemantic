import { Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { paths, useGo } from '@/lib/paths'

export function CalculateButton({ systemId }: { systemId: string }) {
  const go = useGo()
  return (
    <Button size="sm" aria-label="Calculate an impact result" onClick={() => go(paths.results(systemId, 'setup', ''))}>
      <Play className="size-3.5" /> Calculate
    </Button>
  )
}
