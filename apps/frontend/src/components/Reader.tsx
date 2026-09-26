import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { coverTone, savePosition, savedPosition } from '../bookshelf'
import { toBlocks, type Span } from '../bookText'
import { loadUnit, loadLibrary } from '../library'
import type { LibraryBook, LibraryUnit } from '../library'

type Props = { disabled: boolean; onClose: () => void }
type LoadState<T> = { kind: 'loading' } | { kind: 'ready'; data: T } | { kind: 'error'; message: string }

export function Reader({ disabled, onClose }: Props) {
  const [attempt, setAttempt] = useState(0)
  const [library, setLibrary] = useState<LoadState<LibraryBook[]>>({ kind: 'loading' })
  const [open, setOpen] = useState<LibraryBook | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    loadLibrary(controller.signal).then(
      (data) => { if (!controller.signal.aborted) setLibrary({ kind: 'ready', data }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setLibrary({ kind: 'error', message: error instanceof Error ? error.message : 'Unable to load your library.' })
      },
    )
    return () => controller.abort()
  }, [attempt])

  return (
    <aside className={`reader${open ? ' is-reading' : ''}`} aria-label="Library and reading panel">
      {open ? (
        <BookReader book={open} onBack={() => setOpen(null)} onClose={onClose} />
      ) : (
        <Shelf
          library={library}
          disabled={disabled}
          onOpen={setOpen}
          onClose={onClose}
          retry={() => { setLibrary({ kind: 'loading' }); setAttempt((value) => value + 1) }}
        />
      )}
    </aside>
  )
}

function Shelf({ library, disabled, onOpen, onClose, retry }: {
  library: LoadState<LibraryBook[]>
  disabled: boolean
  onOpen: (book: LibraryBook) => void
  onClose: () => void
  retry: () => void
}) {
  return (
    <div className="shelf">
      <header className="shelf-header">
        <div>
          <h2>Library</h2>
          {library.kind === 'ready' && (
            <p>{library.data.length} {library.data.length === 1 ? 'book' : 'books'}</p>
          )}
        </div>
        <button type="button" className="quiet-button" onClick={onClose} aria-label="Close library">Close</button>
      </header>

      {library.kind === 'loading' && <p role="status">Loading your library…</p>}
      {library.kind === 'error' && (
        <div role="alert"><p>{library.message}</p><button type="button" onClick={retry}>Try again</button></div>
      )}
      {library.kind === 'ready' && library.data.length === 0 && <p>No books are available in your library yet.</p>}
      {library.kind === 'ready' && (
        <ul className="shelf-grid">
          {library.data.map((book, index) => (
            <ShelfBook key={book.book_version_id} book={book} tone={coverTone(index)} disabled={disabled} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  )
}

function ShelfBook({ book, tone, disabled, onOpen }: {
  book: LibraryBook
  tone: string
  disabled: boolean
  onOpen: (book: LibraryBook) => void
}) {
  const position = savedPosition(book)
  const index = position ? book.units.findIndex((unit) => unit.unit_id === position) : -1
  return (
    <li>
      <button
        type="button"
        className="shelf-book"
        onClick={() => onOpen(book)}
        disabled={disabled}
        aria-label={`Open ${book.title} by ${book.author}`}
      >
        <BookCover book={book} tone={tone} />
        <span className="shelf-title">{book.title}</span>
        <span className="shelf-author">{book.author}</span>
        <span className="shelf-progress">
          {index >= 0 ? `Continue · ${book.units[index].label}` : `${book.units.length} sections`}
        </span>
        {index >= 0 && (
          <span className="progress-track" aria-hidden="true">
            <span style={{ width: `${((index + 1) / book.units.length) * 100}%` }} />
          </span>
        )}
      </button>
    </li>
  )
}

function BookCover({ book, tone }: { book: LibraryBook; tone: string }) {
  return (
    <span className="book-cover" style={{ '--cover': tone } as CSSProperties} aria-hidden="true">
      <span className="cover-title">{book.title}</span>
      <span className="cover-rule" />
      <span className="cover-author">{book.author}</span>
    </span>
  )
}

function BookReader({ book, onBack, onClose }: { book: LibraryBook; onBack: () => void; onClose: () => void }) {
  const [unitId, setUnitId] = useState(() => savedPosition(book) ?? book.start_unit_id)
  const [contentsOpen, setContentsOpen] = useState(false)
  const top = useRef<HTMLDivElement>(null)
  const index = Math.max(0, book.units.findIndex((item) => item.unit_id === unitId))
  const unit = book.units[index]
  const previous = book.units[index - 1]
  const next = book.units[index + 1]

  function goTo(target: LibraryUnit) {
    setUnitId(target.unit_id)
    setContentsOpen(false)
    top.current?.scrollIntoView({ block: 'start' })
  }

  useEffect(() => savePosition(book, unitId), [book, unitId])

  const parts = new Map<string, { title: string; units: LibraryUnit[] }>()
  for (const item of book.units) {
    const part = parts.get(item.part_id)
    if (part) part.units.push(item)
    else parts.set(item.part_id, { title: item.part_title, units: [item] })
  }

  return (
    <section className="book-reader">
      <div ref={top} />
      <header className="reader-bar">
        <button type="button" className="quiet-button" onClick={onBack}><span aria-hidden="true">←</span> Library</button>
        <div className="reader-bar-title">
          <strong>{book.title}</strong>
          <span>{book.author}</span>
        </div>
        <button
          type="button"
          className="quiet-button"
          aria-expanded={contentsOpen}
          onClick={() => setContentsOpen((value) => !value)}
        >
          Contents
        </button>
        <button type="button" className="quiet-button" onClick={onClose} aria-label="Close library">Close</button>
      </header>

      <div className="reader-progress">
        <span>{unit.label} · {index + 1} of {book.units.length}</span>
        <span className="progress-track" aria-hidden="true">
          <span style={{ width: `${((index + 1) / book.units.length) * 100}%` }} />
        </span>
      </div>

      {contentsOpen && (
        <nav className="contents" aria-label={`Contents of ${book.title}`}>
          {Array.from(parts, ([partId, part]) => (
            <div key={partId}>
              {parts.size > 1 && <p className="eyebrow">{part.title}</p>}
              <ol>
                {part.units.map((item) => (
                  <li key={item.unit_id}>
                    <button
                      type="button"
                      aria-current={item.unit_id === unit.unit_id || undefined}
                      onClick={() => goTo(item)}
                    >
                      {item.label}
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </nav>
      )}

      <article className="page" key={unit.unit_id}>
        <p className="eyebrow">{unit.part_title}</p>
        <h3>{unit.label}</h3>
        <details className="chapter-summary">
          <summary>Chapter summary — contains spoilers</summary>
          <p>{unit.summary}</p>
          <small>Reader-only reference · navigation does not establish a chat spoiler boundary.</small>
        </details>
        <UnitText book={book} unit={unit} />
      </article>

      <nav className="page-turns" aria-label="Chapter navigation">
        {previous ? (
          <button type="button" className="quiet-button" onClick={() => goTo(previous)}>← {previous.label}</button>
        ) : <span />}
        {next && <button type="button" onClick={() => goTo(next)}>{next.label} →</button>}
      </nav>
    </section>
  )
}

function UnitText({ book, unit }: { book: LibraryBook; unit: LibraryUnit }) {
  const [body, setBody] = useState<LoadState<string>>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    loadUnit(book, unit, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setBody({ kind: 'ready', data }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setBody({ kind: 'error', message: error instanceof Error ? error.message : 'Unable to load this text.' })
      },
    )
    return () => controller.abort()
  }, [book, unit, attempt])
  switch (body.kind) {
    case 'loading': return <p role="status">Loading text…</p>
    case 'error': return (
      <div role="alert">
        <p>{body.message}</p>
        <button type="button" onClick={() => { setBody({ kind: 'loading' }); setAttempt((value) => value + 1) }}>Try again</button>
      </div>
    )
    case 'ready': return <BookText text={body.data} />
    default: {
      const _exhaustive: never = body
      return _exhaustive
    }
  }
}

function BookText({ text }: { text: string }) {
  return (
    <div className="chapter-text">
      {toBlocks(text).map((block, index) => block.kind === 'prose' ? (
        <p key={index}><Spans spans={block.spans} /></p>
      ) : (
        <p key={index} className="verse">
          {block.lines.map((line, lineIndex) => <span key={lineIndex}><Spans spans={line} /></span>)}
        </p>
      ))}
    </div>
  )
}

function Spans({ spans }: { spans: Span[] }) {
  return spans.map((span, index) => (span.italic ? <em key={index}>{span.text}</em> : span.text))
}
