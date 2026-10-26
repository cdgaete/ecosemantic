'use client'

import * as React from 'react'
import { ChevronDown } from 'lucide-react'

interface SelectContextValue {
  value: string
  onValueChange: (value: string) => void
  open: boolean
  setOpen: (open: boolean) => void
}

const SelectContext = React.createContext<SelectContextValue | undefined>(undefined)

interface SelectProps {
  value?: string
  onValueChange?: (value: string) => void
  children: React.ReactNode
}

const Select: React.FC<SelectProps> = ({ value = '', onValueChange = () => {}, children }) => {
  const [open, setOpen] = React.useState(false)

  return (
    <SelectContext.Provider value={{ value, onValueChange, open, setOpen }}>
      <div className="relative">{children}</div>
    </SelectContext.Provider>
  )
}

interface SelectTriggerProps {
  children: React.ReactNode
  className?: string
}

const SelectTrigger: React.FC<SelectTriggerProps> = ({ children, className = '' }) => {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error('SelectTrigger must be used within Select')

  return (
    <button
      type="button"
      onClick={() => context.setOpen(!context.open)}
      className={`
        flex h-9 w-full items-center justify-between rounded-md border border-input 
        bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background 
        placeholder:text-muted-foreground focus:outline-none focus:ring-1 
        focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50
        ${className}
      `}
    >
      {children}
      <ChevronDown className="h-4 w-4 opacity-50" />
    </button>
  )
}

interface SelectValueProps {
  placeholder?: string
}

const SelectValue: React.FC<SelectValueProps> = ({ placeholder }) => {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error('SelectValue must be used within Select')

  return <span>{context.value || placeholder}</span>
}

interface SelectContentProps {
  children: React.ReactNode
  className?: string
}

const SelectContent: React.FC<SelectContentProps> = ({ children, className = '' }) => {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error('SelectContent must be used within Select')

  if (!context.open) return null

  return (
    <div
      className={`
        absolute z-50 mt-1 w-full min-w-[8rem] overflow-hidden rounded-md border 
        bg-popover text-popover-foreground shadow-md animate-in fade-in-80
        ${className}
      `}
    >
      <div className="p-1">{children}</div>
    </div>
  )
}

interface SelectItemProps {
  value: string
  children: React.ReactNode
  className?: string
  disabled?: boolean
}

const SelectItem: React.FC<SelectItemProps> = ({
  value,
  children,
  className = '',
  disabled = false,
}) => {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error('SelectItem must be used within Select')

  return (
    <div
      onClick={() => {
        if (disabled) return
        context.onValueChange(value)
        context.setOpen(false)
      }}
      className={`
        relative flex w-full select-none items-center rounded-sm 
        py-1.5 px-2 text-sm outline-none
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-accent hover:text-accent-foreground'}
        ${context.value === value ? 'bg-accent' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  )
}

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem }
