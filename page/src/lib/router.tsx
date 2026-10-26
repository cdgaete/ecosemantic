import { Link, type LinkProps } from 'react-router-dom'
import { withToken } from '@/api/client'

export function AppLink({ to, ...props }: Omit<LinkProps, 'to'> & { to: string }) {
  return <Link to={withToken(to)} {...props} />
}
