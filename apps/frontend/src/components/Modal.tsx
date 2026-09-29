import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

type Props = {
  label: string
  onClose: () => void
  className?: string
  children: ReactNode
}

/** A native modal dialog: Escape, the close button, or a backdrop click dismisses it. */
export function Modal({ label, onClose, className = '', children }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [])

  return (
    <dialog
      ref={dialog}
      className={`modal ${className}`}
      aria-label={label}
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <div className="modal-body">{children}</div>
    </dialog>
  )
}
