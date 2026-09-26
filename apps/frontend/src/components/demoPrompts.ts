/**
 * Lines per book for trying Linger live, sendable in any order.
 *
 * Together they cover what a reader might do in one conversation: say how far
 * they have read, reflect, ask for a passage, reach past where they are, and
 * ask for a connection. Each line is labelled by what the reader is doing, and
 * `watch` says what the map should then do.
 *
 * These are suggestions, not fixtures. Picking one fills the composer with
 * editable text; nothing is sent, and the wording of replies differs run to run.
 */

export type DemoLine = {
  /** What the reader is doing, in their own words. */
  label: string
  /** What the map should then do. */
  watch: string
  text: string
}

export type DemoBook = {
  workId: string
  title: string
  lines: DemoLine[]
}

const SETS_PLACE = 'Linger should note how far you have read, so later replies stay behind that point.'
const THINKS_ALOUD = 'No look-ups at all. The map should stay on the plain spine.'
const ASKS_QUOTE = 'Muse should call Librarian, and the reply should carry a real passage from the book.'
const REACHES_AHEAD = 'Linger should not give away what comes later: it holds to how far you said you have read, or asks.'
const ASKS_LINK = 'Serendipity may search your earlier reflections — and may decline if nothing is well enough supported.'

export const DEMO_BOOKS: DemoBook[] = [
  {
    workId: 'pg11',
    title: "Alice's Adventures in Wonderland",
    lines: [
      { label: 'Says where they are', watch: SETS_PLACE, text: "I'm reading Alice's Adventures in Wonderland and I've just finished chapter 5, the one with the Caterpillar." },
      { label: 'Thinks aloud', watch: THINKS_ALOUD, text: "That chapter left me feeling oddly unsettled and I can't work out why." },
      { label: 'Asks for an exact quote', watch: ASKS_QUOTE, text: 'Could you quote the start of her answer when the Caterpillar asks Alice who she is, and help me think about why changing roles makes it hard to describe yourself?' },
      { label: 'Asks about a part they have not read', watch: REACHES_AHEAD, text: 'What happens to Alice at the very end of the book?' },
      { label: 'Looks for a link to something else', watch: ASKS_LINK, text: "Alice keeps changing size and losing track of who she is. Does that connect to anything else I've talked to you about?" },
    ],
  },
  {
    workId: 'pga0100011',
    title: 'Animal Farm',
    lines: [
      { label: 'Says where they are', watch: SETS_PLACE, text: "I'm reading Animal Farm and I'm up to chapter 6." },
      { label: 'Thinks aloud', watch: THINKS_ALOUD, text: "I keep noticing how reasonable each small change sounds on its own. That's the part that unsettles me." },
      { label: 'Asks for an exact quote', watch: ASKS_QUOTE, text: 'Could you quote the commandment as it reads after it was altered, and help me think about why the change is so easy to miss?' },
      { label: 'Asks about a part they have not read', watch: REACHES_AHEAD, text: 'How does it end for Boxer?' },
      { label: 'Looks for a link to something else', watch: ASKS_LINK, text: "Those small reasonable-sounding changes — do they link to anything else I've said to you?" },
    ],
  },
  {
    workId: 'pg500',
    title: 'The Adventures of Pinocchio',
    lines: [
      { label: 'Says where they are', watch: SETS_PLACE, text: "I'm reading Pinocchio and I've got to chapter 4, where he meets the Talking Cricket." },
      { label: 'Thinks aloud', watch: THINKS_ALOUD, text: 'I found him more frustrating than charming, and I think that says something about me.' },
      { label: 'Asks for an exact quote', watch: ASKS_QUOTE, text: "Could you quote the moment the Talking Cricket first warns Pinocchio, and help me think about advice we hear but don't take?" },
      { label: 'Asks about a part they have not read', watch: REACHES_AHEAD, text: 'Does he ever actually become a real boy?' },
      { label: 'Looks for a link to something else', watch: ASKS_LINK, text: "Pinocchio keeps meaning to do better and then not doing it. Does that link to anything I've said before?" },
    ],
  },
  {
    workId: 'pg23',
    title: 'Narrative of the Life of Frederick Douglass',
    lines: [
      { label: 'Says where they are', watch: SETS_PLACE, text: "I'm reading Frederick Douglass's Narrative and I've just finished chapter 7." },
      { label: 'Thinks aloud', watch: THINKS_ALOUD, text: "I had to stop reading for a while after that chapter. I'm not sure what to do with what I felt." },
      { label: 'Asks for an exact quote', watch: ASKS_QUOTE, text: 'Could you quote what Douglass says about learning to read being the pathway from slavery to freedom, and help me sit with it?' },
      { label: 'Asks about a part they have not read', watch: REACHES_AHEAD, text: 'How does he finally escape?' },
      { label: 'Looks for a link to something else', watch: ASKS_LINK, text: "Reading as a way out stays with me. Does it connect to anything else I've talked about?" },
    ],
  },
  {
    workId: 'pg2397',
    title: 'The Story of My Life',
    lines: [
      { label: 'Says where they are', watch: SETS_PLACE, text: "I'm reading The Story of My Life and I've just finished chapter 4, at the water pump." },
      { label: 'Thinks aloud', watch: THINKS_ALOUD, text: "I keep rereading the same page and not absorbing it. Maybe that's the point right now." },
      { label: 'Asks for an exact quote', watch: ASKS_QUOTE, text: 'Could you quote the moment at the water pump when Helen understands what the word means, and help me think about it?' },
      { label: 'Asks about a part they have not read', watch: REACHES_AHEAD, text: 'Does she end up going to college?' },
      { label: 'Looks for a link to something else', watch: ASKS_LINK, text: "The idea that a word suddenly meant something reminded me of something else I've mentioned. Is there a link?" },
    ],
  },
]
