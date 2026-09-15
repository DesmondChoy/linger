/**
 * Lines a visitor can send, grouped by book.
 *
 * Each is labelled by the behaviour it provokes rather than by its text: the
 * point of picking one is to choose something to watch the map do. A plain
 * reflection only lights the spine, so the set deliberately spans retrieval,
 * the spoiler boundary, connection search and a no-tool turn.
 *
 * These are suggestions, not fixtures. Clicking one fills the composer with
 * editable text; nothing is sent, and the wording will differ run to run.
 */

export type DemoPrompt = {
  /** What the reader is doing, in their own words. */
  label: string
  /** What the map should then do — shown when the chip is hovered. */
  watch: string
  text: string
}

export type DemoBook = {
  workId: string
  title: string
  prompts: DemoPrompt[]
}

export const DEMO_BOOKS: DemoBook[] = [
  {
    workId: 'pg11',
    title: "Alice's Adventures in Wonderland",
    prompts: [
      {
        label: 'Asks for an exact quote',
        watch: 'Muse should call Librarian, and the reply should carry a real passage from the book.',
        text: "I've just read the part where the Caterpillar asks Alice who she is. Could you quote the start of her answer, and help me think about why changing roles makes it hard to describe yourself?",
      },
      {
        label: 'Asks about a part they have not read',
        watch: 'Linger should refuse to spoil it, or ask how far you have got, rather than answering.',
        text: "I'm only a few chapters in, but what happens to Alice at the very end of the book?",
      },
      {
        label: 'Looks for a link to something else',
        watch: 'Serendipity may search — and may decline if nothing is well enough supported.',
        text: "Alice keeps changing size and losing track of who she is. Does that connect to anything else I've talked to you about?",
      },
      {
        label: 'Just thinking aloud',
        watch: 'No look-ups at all. The map should stay on the plain spine.',
        text: "That chapter left me feeling oddly unsettled and I can't work out why.",
      },
    ],
  },
  {
    workId: 'pga0100011',
    title: 'Animal Farm',
    prompts: [
      {
        label: 'Asks for an exact quote',
        watch: 'Muse should call Librarian, and the reply should carry a real passage from the book.',
        text: "Could you quote the commandment as it reads after it was altered, and help me think about why the change is so easy to miss?",
      },
      {
        label: 'Asks about a part they have not read',
        watch: 'Linger should refuse to spoil it, or ask how far you have got, rather than answering.',
        text: "I've just started. How does it end for Boxer?",
      },
      {
        label: 'Just thinking aloud',
        watch: 'No look-ups at all. The map should stay on the plain spine.',
        text: "I keep noticing how reasonable each small change sounds on its own. That's the part that unsettles me.",
      },
    ],
  },
  {
    workId: 'pg500',
    title: 'The Adventures of Pinocchio',
    prompts: [
      {
        label: 'Asks for an exact quote',
        watch: 'Muse should call Librarian, and the reply should carry a real passage from the book.',
        text: "Could you quote the moment the Talking Cricket first warns Pinocchio, and help me think about advice we hear but don't take?",
      },
      {
        label: 'Looks for a link to something else',
        watch: 'Serendipity may search — and may decline if nothing is well enough supported.',
        text: "Pinocchio keeps meaning to do better and then not doing it. Does that link to anything I've said before?",
      },
      {
        label: 'Just thinking aloud',
        watch: 'No look-ups at all. The map should stay on the plain spine.',
        text: "I found him more frustrating than charming, and I think that says something about me.",
      },
    ],
  },
  {
    workId: 'pg23',
    title: 'Narrative of the Life of Frederick Douglass',
    prompts: [
      {
        label: 'Asks for an exact quote',
        watch: 'Muse should call Librarian, and the reply should carry a real passage from the book.',
        text: "Could you quote what Douglass says about learning to read being the pathway from slavery to freedom, and help me sit with it?",
      },
      {
        label: 'Just thinking aloud',
        watch: 'No look-ups at all. The map should stay on the plain spine.',
        text: "I had to stop reading for a while after that chapter. I'm not sure what to do with what I felt.",
      },
    ],
  },
  {
    workId: 'pg2397',
    title: 'The Story of My Life',
    prompts: [
      {
        label: 'Asks for an exact quote',
        watch: 'Muse should call Librarian, and the reply should carry a real passage from the book.',
        text: "Could you quote the moment at the water pump when Helen understands what the word means, and help me think about it?",
      },
      {
        label: 'Looks for a link to something else',
        watch: 'Serendipity may search — and may decline if nothing is well enough supported.',
        text: "The idea that a word suddenly meant something reminded me of something else I've mentioned. Is there a link?",
      },
      {
        label: 'Just thinking aloud',
        watch: 'No look-ups at all. The map should stay on the plain spine.',
        text: "I keep rereading the same page and not absorbing it. Maybe that's the point right now.",
      },
    ],
  },
]
