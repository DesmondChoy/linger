import { useState } from 'react'

type Props = {
  disabled: boolean
}

const alice = {
  id: 'alice-wonderland', title: 'Alice’s Adventures in Wonderland', author: 'Lewis Carroll',
  source: 'Project Gutenberg · Public domain', sourceUrl: 'https://www.gutenberg.org/files/11/11-h/11-h.htm', coverUrl: 'https://www.gutenberg.org/cache/epub/11/pg11.cover.medium.jpg',
  chapterAnchor: (chapter: number) => `chap${String(chapter).padStart(2, '0')}`,
  chapters: ['Down the Rabbit-Hole', 'The Pool of Tears', 'A Caucus-Race and a Long Tale', 'The Rabbit Sends in a Little Bill', 'Advice from a Caterpillar', 'Pig and Pepper', 'A Mad Tea-Party', 'The Queen’s Croquet-Ground', 'The Mock Turtle’s Story', 'The Lobster Quadrille', 'Who Stole the Tarts?', 'Alice’s Evidence'],
  summaries: ['Alice notices the White Rabbit worrying about being late and follows him down a rabbit-hole. Her long fall carries her into a hall of locked doors, where she changes size after eating and drinking in order to reach the garden.', 'Alice’s rapid changes in size leave her crying a pool of tears. She meets a Mouse and several animals, then they all struggle ashore after being swept along in the water.', 'The animals argue about how to get dry, so the Dodo proposes a Caucus-race with no clear beginning or end. When it finishes, the Dodo declares that everyone has won and makes Alice distribute prizes.', 'The White Rabbit mistakes Alice for his maid and sends her into his house. She grows so large inside that she becomes stuck, while the Rabbit and other animals try increasingly strange ways to get her out.', 'Alice meets the Caterpillar on a mushroom, and he repeatedly asks her who she is. He tells her that different sides of the mushroom will make her grow or shrink, which Alice uses to manage her changing body.', 'Alice enters the Duchess’s violent, pepper-filled kitchen, where a baby turns into a pig. Outside, the Cheshire Cat appears and disappears at will, then directs Alice toward the March Hare and the Hatter.', 'Alice joins the March Hare, Hatter, and Dormouse at a tea party that never moves past six o’clock. Their riddles and interruptions frustrate her until she leaves the table.', 'Alice reaches the Queen’s garden, where gardeners are terrified of being ordered beheaded. She plays a chaotic game of croquet with flamingos and hedgehogs, while the Queen repeatedly calls for executions.', 'The Gryphon takes Alice to meet the Mock Turtle, who mournfully tells her about his schooldays under the sea. His story turns familiar lessons into puns and absurd subjects.', 'The Mock Turtle and Gryphon explain and perform the Lobster Quadrille. Alice listens to the Mock Turtle sing and then is hurried away when the trial is about to begin.', 'Alice attends the Knave of Hearts’ trial for allegedly stealing the Queen’s tarts. Witnesses give nonsensical evidence, and the court keeps changing its rules as the King tries to force a verdict.', 'Alice grows to her normal size during the trial and openly challenges the court’s authority. The cards rise around her, and she wakes to discover that the entire adventure has been a dream.'],
}

export function Reader({ disabled }: Props) {
  const [bookOpen, setBookOpen] = useState(false)
  const [activeChapter, setActiveChapter] = useState(1)
  const [summaryVisible, setSummaryVisible] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const bookUrl = `${alice.sourceUrl}#${alice.chapterAnchor(activeChapter)}`

  function openBook() {
    setBookOpen(true)
    setActiveChapter(1)
    setSummaryVisible(false)
  }

  function closeBook() {
    setBookOpen(false)
    setActiveChapter(1)
    setSummaryVisible(false)
  }

  function selectChapter(chapter: number) {
    setActiveChapter(chapter)
    setSummaryVisible(false)
  }

  return (
    <aside className={`reader${expanded ? ' expanded' : ''}`} aria-label="Library and reading panel">
      <button
        type="button"
        className="reader-toggle"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        {expanded ? 'Narrow library' : 'Expand library'}
      </button>
      {bookOpen ? (
        <section className="reader-view">
          <button type="button" className="back-to-library" onClick={closeBook}>
            <span aria-hidden="true">←</span> Back to library
          </button>
          <div className="reader-progress">
            <div>
              <p className="eyebrow">Reader</p>
              <h2>{alice.title}</h2>
              <p className="reader-author">{alice.author}</p>
            </div>
            <label className="chapter-select">
              Go to chapter
              <select value={activeChapter} onChange={(event) => selectChapter(Number(event.target.value))}>
                {alice.chapters.map((chapter, index) => <option key={chapter} value={index + 1}>Chapter {index + 1} — {chapter}</option>)}
              </select>
            </label>
          </div>
          <section className="chapter-summary" aria-live="polite">
            <p className="eyebrow">Chapter summary</p>
            {summaryVisible ? (
              <p>{alice.summaries[activeChapter - 1]}</p>
            ) : (
              <button type="button" onClick={() => setSummaryVisible(true)}>
                Reveal summary — contains Chapter {activeChapter} spoilers
              </button>
            )}
            <small>Reader-only reference · chapter navigation does not establish a chat spoiler boundary.</small>
          </section>
          <article className="chapter-reader">
            <p className="eyebrow">Chapter {activeChapter}</p>
            <h3>{alice.chapters[activeChapter - 1]}</h3>
            <p className="book-source">Reading from <a href={bookUrl} target="_blank" rel="noreferrer">{alice.source}</a>.</p>
            <iframe key={activeChapter} title={`${alice.title}, Chapter ${activeChapter}`} src={bookUrl} />
          </article>
        </section>
      ) : (
        <div className="library-view">
          <div className="reader-heading">
            <p className="eyebrow">Your library</p>
            <h2>Reading space</h2>
            <p>Choose a book from your shelf to begin reading.</p>
          </div>

          <div className="library-list">
            <section className="book-card">
              <div className={`book-cover ${alice.id}`}><img src={alice.coverUrl} alt={`${alice.title} cover`} /></div>
              <div>
                <h3>{alice.title}</h3>
                <p>{alice.author} · {alice.source}</p>
              </div>
              <button type="button" className="choose-book" onClick={openBook} disabled={disabled}>
                Open book
              </button>
            </section>
          </div>
        </div>
      )}
    </aside>
  )
}
