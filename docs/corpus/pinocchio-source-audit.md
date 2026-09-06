# Pinocchio source audit

Immutable source: `data/gutenberg/the-adventures-of-pinocchio.txt`.
Project Gutenberg ebook 500, Carlo Collodi, translated by Carol Della Chiesa;
release January 12, 2006, updated September 28, 2020 (source header).
The source carries the Gutenberg reuse notice and complete licence; its header
identifies https://www.gutenberg.org/ebooks/500 as its edition page. The original
and its licence remain intact alongside the derived corpus.

239,455 bytes; SHA-256 `6bdc173408a95ee683f0013e8a098fac66965af34bbcb9c52cfe632d23f76ff9`.
Strict UTF-8, no BOM, 6,224 LF characters, no CR or CRLF.
One Gutenberg START marker at line 29 and one END marker at line 5875.
There is no contents page or repeated chapter heading. All 36 numbered headings
are consecutive. No prologue, appendix, illustrations or separate THE END occurs.
Exclude lines 1–56 (wrapper, credits, proofreading note, title and translator),
blank chapter separators, and lines 5865 onward (blank padding and licence).

Retain the inline footnotes at lines 163 (`     * Cornmeal mush`) and 382
(`     * A military policeman`), the indented epitaph at 2696–2700, circus poster
at 4841–4859 including its internal blank lines, and purse inscription at
5823–5825. Preserve curly quotation marks, underscores, double hyphens, unusual
spaces (including the initial space on line 3020), and apparent errors such as
`a Crow, and Owl` and `ugly Gab` without correction or reflow. Narrative source
bodies are exact contiguous line slices with one terminal LF. Titles join source
hard wraps with one space; existing internal spaces remain (chapter 3 has two
spaces in `pranks  of`). Titles' original wraps remain recoverable in source ranges.

Routing proposals were curated after reading every chapter and reviewed against
its body. They deliberately avoid importing title-only promises into descriptions
(e.g. the actual departure to the Land of Toys occurs in chapter 31, not 30).
The shared deterministic lifecycle validates all nonsemantic fields and exact
bodies; canonical metadata remains reviewable and editable in Git.

Ranges below are inclusive, one-based. Source includes heading and title through
last narrative line; body starts after the title and blank separator and ends on
the same last narrative line. Only inter-unit blank padding is omitted.

| Chapter | Source lines | Body lines | Exact title (wraps joined) |
| --- | --- | --- | --- |
| 1 | 57–142 | 63–142 | How it happened that Mastro Cherry, carpenter, found a piece of wood that wept and laughed like a child. |
| 2 | 147–278 | 154–278 | Mastro Cherry gives the piece of wood to his friend Geppetto, who takes it to make himself a Marionette that will dance, fence, and turn somersaults. |
| 3 | 283–424 | 289–424 | As soon as he gets home, Geppetto fashions the Marionette and calls it Pinocchio. The first pranks  of the Marionette. |
| 4 | 429–523 | 436–523 | The story of Pinocchio and the Talking Cricket, in which one sees that bad children do not like to be corrected by those who know more than they do. |
| 5 | 528–598 | 534–598 | Pinocchio is hungry and looks for an egg to cook himself an omelet; but, to his surprise, the omelet flies out of the window. |
| 6 | 603–663 | 609–663 | Pinocchio falls asleep with his feet on a foot warmer, and awakens the next day with his feet all burned off. |
| 7 | 668–782 | 673–782 | Geppetto returns home and gives his own breakfast to the Marionette |
| 8 | 787–886 | 793–886 | Geppetto makes Pinocchio a new pair of feet, and sells his coat to buy him an A-B-C book. |
| 9 | 891–988 | 897–988 | Pinocchio sells his A-B-C book to pay his way into the Marionette Theater. |
| 10 | 993–1078 | 1000–1078 | The Marionettes recognize their brother Pinocchio, and greet him with loud cheers; but the Director, Fire Eater, happens along and poor Pinocchio almost loses his life. |
| 11 | 1083–1197 | 1089–1197 | Fire Eater sneezes and forgives Pinocchio, who saves his friend, Harlequin, from death. |
| 12 | 1202–1382 | 1208–1382 | Fire Eater gives Pinocchio five gold pieces for his father, Geppetto; but the Marionette meets a Fox and a Cat and follows them. |
| 13 | 1387–1512 | 1392–1512 | The Inn of the Red Lobster |
| 14 | 1517–1625 | 1523–1625 | Pinocchio, not having listened to the good advice of the Talking Cricket, falls into the hands of the Assassins. |
| 15 | 1630–1723 | 1636–1723 | The Assassins chase Pinocchio, catch him, and hang him to the branch of a giant oak tree. |
| 16 | 1728–1849 | 1735–1849 | The Lovely Maiden with Azure Hair sends for the poor Marionette, puts him to bed, and calls three Doctors to tell her if Pinocchio is dead or alive. |
| 17 | 1854–2060 | 1861–2060 | Pinocchio eats sugar, but refuses to take medicine. When the undertakers come for him, he drinks the medicine and feels better. Afterwards he tells a lie and, in punishment, his nose grows longer and longer. |
| 18 | 2065–2238 | 2071–2238 | Pinocchio finds the Fox and the Cat again, and goes with them to sow the gold pieces in the Field of Wonders. |
| 19 | 2243–2359 | 2249–2359 | Pinocchio is robbed of his gold pieces and, in punishment, is sentenced to four months in prison. |
| 20 | 2364–2448 | 2370–2448 | Freed from prison, Pinocchio sets out to return to the Fairy; but on the way he meets a Serpent and later is caught in a trap. |
| 21 | 2453–2540 | 2459–2540 | Pinocchio is caught by a Farmer, who uses him as a watchdog for his chicken coop. |
| 22 | 2545–2668 | 2551–2668 | Pinocchio discovers the thieves and, as a reward for faithfulness, he regains his liberty. |
| 23 | 2673–2854 | 2680–2854 | Pinocchio weeps upon learning that the Lovely Maiden with Azure Hair is dead. He meets a Pigeon, who carries him to the seashore. He throws himself into the sea to go to the aid of his father. |
| 24 | 2859–3070 | 2865–3070 | Pinocchio reaches the Island of the Busy Bees and finds the Fairy once more. |
| 25 | 3075–3204 | 3081–3204 | Pinocchio promises the Fairy to be good and to study, as he is growing tired of being a Marionette, and wishes to become a real boy. |
| 26 | 3209–3313 | 3215–3313 | Pinocchio goes to the seashore with his friends to see the Terrible Shark. |
| 27 | 3318–3554 | 3324–3554 | The great battle between Pinocchio and his playmates. One is wounded. Pinocchio is arrested. |
| 28 | 3559–3735 | 3564–3735 | Pinocchio runs the danger of being fried in a pan like a fish |
| 29 | 3740–4017 | 3747–4017 | Pinocchio returns to the Fairy’s house and she promises him that, on the morrow, he will cease to be a Marionette and become a boy. A wonderful party of coffee-and-milk to celebrate the great event. |
| 30 | 4022–4255 | 4028–4255 | Pinocchio, instead of becoming a boy, runs away to the Land of Toys with his friend, Lamp-Wick. |
| 31 | 4260–4483 | 4266–4483 | After five months of play, Pinocchio wakes up one fine morning and finds a great surprise awaiting him. |
| 32 | 4488–4731 | 4494–4731 | Pinocchio’s ears become like those of a Donkey. In a little while he changes into a real Donkey and begins to bray. |
| 33 | 4736–5006 | 4743–5006 | Pinocchio, having become a Donkey, is bought by the owner of a Circus, who wants to teach him to do tricks. The Donkey becomes lame and is sold to a man who wants to use his skin for a drumhead. |
| 34 | 5011–5261 | 5018–5261 | Pinocchio is thrown into the sea, eaten by fishes, and becomes a Marionette once more. As he swims to land, he is swallowed by the Terrible Shark. |
| 35 | 5266–5440 | 5272–5440 | In the Shark’s body Pinocchio finds whom? Read this chapter, my children, and you will know. |
| 36 | 5445–5864 | 5450–5864 | Pinocchio finally ceases to be a Marionette and becomes a boy |
