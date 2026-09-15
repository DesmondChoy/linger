import { useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react'

export type ComposerHandle = {
  /** Put text in the box, focused and editable. Never sends it. */
  fill: (text: string) => void
}

type Props = {
  disabled: boolean
  onSend: (message: string) => void
  ref?: Ref<ComposerHandle>
}

export function Composer({ disabled, onSend, ref }: Props) {
  const [value, setValue] = useState('')
  const field = useRef<HTMLTextAreaElement>(null)

  useImperativeHandle(ref, () => ({
    fill(text: string) {
      setValue(text)
      // Focus with the caret at the end so the suggestion reads as a draft the
      // reader owns, not as a command that has already run.
      requestAnimationFrame(() => {
        const element = field.current
        if (!element) return
        element.focus()
        element.setSelectionRange(text.length, text.length)
      })
    },
  }), [])

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  // Enter sends, Shift+Enter inserts a newline.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        ref={field}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Tell Linger what you’re reading, watching, or thinking about…"
        rows={1}
        autoFocus
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  )
}
