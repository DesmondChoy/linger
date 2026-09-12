import { useEffect, useState } from 'react'
import { loadChapter, loadLibrary } from '../library'
import type { LibraryBook, LibraryChapter } from '../library'

type Props = { disabled: boolean }
type LoadState<T> = { kind: 'loading' } | { kind: 'ready'; data: T } | { kind: 'error'; message: string }

export function Reader({ disabled }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [attempt, setAttempt] = useState(0)
  return (
    <aside className={`reader${expanded ? ' expanded' : ''}`} aria-label="Library and reading panel">
      <button type="button" className="reader-toggle" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        {expanded ? 'Narrow library' : 'Expand library'}
      </button>
      <Library key={attempt} disabled={disabled} retry={() => setAttempt((value) => value + 1)} />
    </aside>
  )
}

function Library({ disabled, retry }: Props & { retry: () => void }) {
  const [library, setLibrary] = useState<LoadState<LibraryBook[]>>({ kind: 'loading' })
  const [selected, setSelected] = useState<LibraryBook | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    loadLibrary(controller.signal).then(
      (data) => { if (!controller.signal.aborted) setLibrary({ kind: 'ready', data }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setLibrary({ kind: 'error', message: error instanceof Error ? error.message : 'Unable to load your library.' })
      },
    )
    return () => controller.abort()
  }, [])

  if (selected) return <BookReader book={selected} close={retry} />
  return (
    <div className="library-view">
      <div className="reader-heading">
        <p className="eyebrow">Your library</p>
        <h2>Reading space</h2>
        <p>Choose a book from your shelf to begin reading.</p>
      </div>
      {library.kind === 'loading' && <p role="status">Loading your library…</p>}
      {library.kind === 'error' && <div role="alert"><p>{library.message}</p><button type="button" onClick={retry}>Try again</button></div>}
      {library.kind === 'ready' && (
        <div className="library-list">
          {library.data.length === 0 && <p>No books are available in your library yet.</p>}
          {library.data.map((book) => (
            <section className="book-card" key={book.book_version_id}>
              <div className="book-cover" aria-hidden="true">{book.title.slice(0, 1)}</div>
              <div><h3>{book.title}</h3><p>{book.author} · {book.chapters.length} chapters</p></div>
              <button type="button" className="choose-book" onClick={() => setSelected(book)} disabled={disabled} aria-label={`Open ${book.title}`}>
                Open book
              </button>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function BookReader({ book, close }: { book: LibraryBook; close: () => void }) {
  const [chapterNumber, setChapterNumber] = useState(book.chapters[0]?.number)
  const chapter = book.chapters.find((item) => item.number === chapterNumber)
  return (
    <section className="reader-view">
      <button type="button" className="back-to-library" onClick={close}><span aria-hidden="true">←</span> Back to library</button>
      <div className="reader-progress">
        <div><p className="eyebrow">Reader</p><h2>{book.title}</h2><p className="reader-author">{book.author}</p></div>
        <label className="chapter-select">
          Go to chapter
          <select value={chapterNumber} onChange={(event) => setChapterNumber(Number(event.target.value))}>
            {book.chapters.map((item) => <option key={item.number} value={item.number}>Chapter {item.number} — {item.title}</option>)}
          </select>
        </label>
      </div>
      {chapter && <ChapterReader key={chapter.number} book={book} chapter={chapter} />}
    </section>
  )
}

function ChapterReader({ book, chapter }: { book: LibraryBook; chapter: LibraryChapter }) {
  const [summaryVisible, setSummaryVisible] = useState(false)
  const [attempt, setAttempt] = useState(0)
  return (
    <>
      <section className="chapter-summary" aria-live="polite">
        <p className="eyebrow">Chapter summary</p>
        {summaryVisible ? <p>{chapter.summary}</p> : (
          <button type="button" onClick={() => setSummaryVisible(true)}>Reveal summary — contains Chapter {chapter.number} spoilers</button>
        )}
        <small>Reader-only reference · chapter navigation does not establish a chat spoiler boundary.</small>
      </section>
      <article className="chapter-reader">
        <p className="eyebrow">Chapter {chapter.number}</p><h3>{chapter.title}</h3>
        <ChapterText key={attempt} book={book} chapter={chapter} retry={() => setAttempt((value) => value + 1)} />
      </article>
    </>
  )
}

function ChapterText({ book, chapter, retry }: { book: LibraryBook; chapter: LibraryChapter; retry: () => void }) {
  const [body, setBody] = useState<LoadState<string>>({ kind: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    loadChapter(book, chapter, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setBody({ kind: 'ready', data }) },
      (error: unknown) => {
        if (!controller.signal.aborted) setBody({ kind: 'error', message: error instanceof Error ? error.message : 'Unable to load this chapter.' })
      },
    )
    return () => controller.abort()
  }, [book, chapter])
  switch (body.kind) {
    case 'loading': return <p role="status">Loading chapter…</p>
    case 'error': return <div role="alert"><p>{body.message}</p><button type="button" onClick={retry}>Try again</button></div>
    case 'ready': return <div className="chapter-text">{body.data}</div>
    default: {
      const _exhaustive: never = body
      return _exhaustive
    }
  }
}
