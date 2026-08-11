import { useState } from 'react'

type Props = {
  disabled: boolean
}

type LibraryBook = {
  id: 'alice-wonderland' | 'animal-farm'
  title: string
  author: string
  source: string
  sourceUrl: string
  chapters: string[]
  summaries: string[]
  coverUrl: string
  chapterAnchor: (chapter: number) => string
}

const books: LibraryBook[] = [
  {
    id: 'alice-wonderland', title: 'Alice’s Adventures in Wonderland', author: 'Lewis Carroll',
    source: 'Project Gutenberg · Public domain', sourceUrl: 'https://www.gutenberg.org/files/11/11-h/11-h.htm', coverUrl: 'https://www.gutenberg.org/cache/epub/11/pg11.cover.medium.jpg',
    chapterAnchor: (chapter) => `chap${String(chapter).padStart(2, '0')}`,
    chapters: ['Down the Rabbit-Hole', 'The Pool of Tears', 'A Caucus-Race and a Long Tale', 'The Rabbit Sends in a Little Bill', 'Advice from a Caterpillar', 'Pig and Pepper', 'A Mad Tea-Party', 'The Queen’s Croquet-Ground', 'The Mock Turtle’s Story', 'The Lobster Quadrille', 'Who Stole the Tarts?', 'Alice’s Evidence'],
    summaries: ['Alice notices the White Rabbit worrying about being late and follows him down a rabbit-hole. Her long fall carries her into a hall of locked doors, where she changes size after eating and drinking in order to reach the garden.', 'Alice’s rapid changes in size leave her crying a pool of tears. She meets a Mouse and several animals, then they all struggle ashore after being swept along in the water.', 'The animals argue about how to get dry, so the Dodo proposes a Caucus-race with no clear beginning or end. When it finishes, the Dodo declares that everyone has won and makes Alice distribute prizes.', 'The White Rabbit mistakes Alice for his maid and sends her into his house. She grows so large inside that she becomes stuck, while the Rabbit and other animals try increasingly strange ways to get her out.', 'Alice meets the Caterpillar on a mushroom, and he repeatedly asks her who she is. He tells her that different sides of the mushroom will make her grow or shrink, which Alice uses to manage her changing body.', 'Alice enters the Duchess’s violent, pepper-filled kitchen, where a baby turns into a pig. Outside, the Cheshire Cat appears and disappears at will, then directs Alice toward the March Hare and the Hatter.', 'Alice joins the March Hare, Hatter, and Dormouse at a tea party that never moves past six o’clock. Their riddles and interruptions frustrate her until she leaves the table.', 'Alice reaches the Queen’s garden, where gardeners are terrified of being ordered beheaded. She plays a chaotic game of croquet with flamingos and hedgehogs, while the Queen repeatedly calls for executions.', 'The Gryphon takes Alice to meet the Mock Turtle, who mournfully tells her about his schooldays under the sea. His story turns familiar lessons into puns and absurd subjects.', 'The Mock Turtle and Gryphon explain and perform the Lobster Quadrille. Alice listens to the Mock Turtle sing and then is hurried away when the trial is about to begin.', 'Alice attends the Knave of Hearts’ trial for allegedly stealing the Queen’s tarts. Witnesses give nonsensical evidence, and the court keeps changing its rules as the King tries to force a verdict.', 'Alice grows to her normal size during the trial and openly challenges the court’s authority. The cards rise around her, and she wakes to discover that the entire adventure has been a dream.'],
  },
  {
    id: 'animal-farm', title: 'Animal Farm', author: 'George Orwell',
    source: 'Project Gutenberg Australia', sourceUrl: 'https://gutenberg.net.au/ebooks01/0100011h.html', coverUrl: 'https://www.fulltable.com/vts/b/bc/A/03.jpg',
    chapterAnchor: (chapter) => `ch${chapter}`,
    chapters: ['Chapter I', 'Chapter II', 'Chapter III', 'Chapter IV', 'Chapter V', 'Chapter VI', 'Chapter VII', 'Chapter VIII', 'Chapter IX', 'Chapter X'],
    summaries: ['Mr Jones neglects the animals, and Old Major gathers them in the barn to describe a future without human masters. He teaches them “Beasts of England” and urges them to prepare for rebellion before dying a few days later.', 'The animals unexpectedly drive Mr Jones and his men from Manor Farm when they are not fed. They rename it Animal Farm, destroy the tools of human control, and paint the Seven Commandments of Animalism on the barn wall.', 'The pigs take charge of organising the farm while Snowball and Napoleon compete for influence. Snowball leads the animals in defending the farm during the Battle of the Cowshed, but the pigs quietly reserve the milk and apples for themselves.', 'Snowball promotes plans for a windmill, while Napoleon raises a group of puppies in private. At a public meeting, Napoleon uses the grown dogs to chase Snowball from the farm and declares that meetings will no longer be held.', 'Napoleon takes credit for the windmill idea and demands harder work from everyone. When the windmill is destroyed in a storm, he blames Snowball and begins using fear of the exiled pig to explain every setback.', 'The pigs begin trading with humans and move into the farmhouse despite earlier promises. When the animals object, Squealer persuades them that the rules have always allowed the pigs’ comforts and that the windmill will make life easier.', 'Napoleon stages public confessions and has the dogs execute several animals accused of helping Snowball. The remaining animals are shaken, and Clover notices that the commandment against killing has acquired the words “without cause.”', 'The humans attack Animal Farm and destroy the rebuilt windmill, but the animals drive them away in the Battle of the Windmill. Napoleon calls it a victory even though the animals have lost months of work and many are injured.', 'The animals struggle through shortages while the pigs enjoy increasing privileges. Boxer works himself beyond his strength; when he collapses, the pigs sell him to a knacker and use the money to buy whisky.', 'Years later, the farm is prosperous for the pigs but not for the other animals. The Seven Commandments have been reduced to one rule, and the animals watch the pigs dine with humans until they can no longer tell the two apart.'],
  },
]

export function Reader({ disabled }: Props) {
  const [selectedBookId, setSelectedBookId] = useState<LibraryBook['id'] | null>(null)
  const [activeChapter, setActiveChapter] = useState(1)
  const [expanded, setExpanded] = useState(false)
  const selectedBook = books.find((book) => book.id === selectedBookId) ?? null
  const bookUrl = selectedBook ? `${selectedBook.sourceUrl}#${selectedBook.chapterAnchor(activeChapter)}` : ''

  function openBook(book: LibraryBook) {
    setSelectedBookId(book.id)
    setActiveChapter(1)
  }

  function closeBook() {
    setSelectedBookId(null)
    setActiveChapter(1)
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
      {selectedBook ? (
        <section className="reader-view">
          <button type="button" className="back-to-library" onClick={closeBook}>
            <span aria-hidden="true">←</span> Back to library
          </button>
          <div className="reader-progress">
            <div>
              <p className="eyebrow">Reader</p>
              <h2>{selectedBook.title}</h2>
              <p className="reader-author">{selectedBook.author}</p>
            </div>
            <label className="chapter-select">
              Go to chapter
              <select value={activeChapter} onChange={(event) => setActiveChapter(Number(event.target.value))}>
                {selectedBook.chapters.map((chapter, index) => <option key={chapter} value={index + 1}>Chapter {index + 1} — {chapter}</option>)}
              </select>
            </label>
          </div>
          <section className="chapter-summary" aria-live="polite">
            <p className="eyebrow">Chapter summary</p>
            <p>{selectedBook.summaries[activeChapter - 1]}</p>
            <small>Reader-only reference · selecting a chapter does not update chat or agents.</small>
          </section>
          <article className="chapter-reader">
            <p className="eyebrow">Chapter {activeChapter}</p>
            <h3>{selectedBook.chapters[activeChapter - 1]}</h3>
            <p className="book-source">Reading from <a href={bookUrl} target="_blank" rel="noreferrer">{selectedBook.source}</a>.</p>
            <iframe key={`${selectedBook.id}-${activeChapter}`} title={`${selectedBook.title}, Chapter ${activeChapter}`} src={bookUrl} />
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
            {books.map((book) => (
              <section key={book.id} className="book-card">
                <div className={`book-cover ${book.id}`}><img src={book.coverUrl} alt={`${book.title} cover`} /></div>
                <div>
                  <h3>{book.title}</h3>
                  <p>{book.author} · {book.source}</p>
                </div>
                <button type="button" className="choose-book" onClick={() => openBook(book)} disabled={disabled}>
                  Open book
                </button>
              </section>
            ))}
          </div>

          <section className="upload-card">
            <p className="eyebrow">Coming next</p>
            <h3>Add your own book</h3>
            <p>EPUB and PDF uploads will be structured, indexed, and added to this same library.</p>
            <button type="button" disabled>Upload a book</button>
          </section>
        </div>
      )}
    </aside>
  )
}
