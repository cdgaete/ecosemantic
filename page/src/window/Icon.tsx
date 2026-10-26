import {
  BarChart3,
  Database,
  Dices,
  Factory,
  Folder,
  History,
  Layers,
  Leaf,
  MessageSquare,
  Package,
  Sigma,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export type IconName =
  | 'system'
  | 'process'
  | 'product'
  | 'elementary'
  | 'parameter'
  | 'result'
  | 'database'
  | 'folder'
  | 'log'
  | 'request'
  | 'simulation'

const ICONS: Record<IconName, LucideIcon> = {
  system: Layers,
  process: Factory,
  product: Package,
  elementary: Leaf,
  parameter: Sigma,
  result: BarChart3,
  database: Database,
  folder: Folder,
  log: History,
  request: MessageSquare,
  simulation: Dices,
}

export function Icon({ name, className }: { name: IconName; className?: string }) {
  const Glyph = ICONS[name]
  return <Glyph aria-hidden="true" className={cn('inline-block size-4 shrink-0', `text-role-${name}`, className)} />
}
