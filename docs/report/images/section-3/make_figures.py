"""Generate the Section 3 report figures as SVG, in the style of the Section 2 figures.

Grey boxes are agents, white boxes are application code, and dashed pills are
fixed replies that end the turn. Run from the repository root:

    python3 docs/report/images/section-3/make_figures.py
    NODE_PATH=$(npm root -g) node docs/report/images/section-3/render_png.mjs
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).parent
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
AGENT = "#e6e6e6"
PANEL = "#f4f4f4"
INK = "#111"
SOFT = "#444"


class Figure:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.parts: list[str] = []

    def text(self, x, y, s, size=12, weight="normal", anchor="middle", fill=INK, style="normal"):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-style="{style}" fill="{fill}">{escape(s)}</text>'
        )

    def box(self, x, y, w, h, title, lines=(), kind="app", title_size=13):
        fill = {"app": "#fff", "agent": AGENT, "exit": "#fff", "note": "#fff", "panel": PANEL}[kind]
        rx = 16 if kind == "exit" else 3
        dash = ' stroke-dasharray="5 3"' if kind == "exit" else ""
        stroke = "#999" if kind == "note" else INK
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.2"{dash}/>'
        )
        if kind == "panel":
            self.text(x + 12, y + 20, title, size=title_size, weight="bold", anchor="start")
            return
        block = 16 + 15 * len(lines)
        top = y + (h - block) / 2 + 12
        self.text(x + w / 2, top, title, size=title_size, weight="bold")
        for i, line in enumerate(lines):
            self.text(x + w / 2, top + 17 + 15 * i, line, size=11.5, fill=SOFT)

    def arrow(self, pts, label=None, at=None, anchor="middle", dashed=False, both=False):
        d = " ".join(f"{'M' if i == 0 else 'L'}{px},{py}" for i, (px, py) in enumerate(pts))
        dash = ' stroke-dasharray="4 3"' if dashed else ""
        start = ' marker-start="url(#a)"' if both else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="1.2"{dash}{start} marker-end="url(#a)"/>'
        )
        if label:
            lx, ly = at if at else ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2 - 6)
            for i, line in enumerate(label.split("\n")):
                self.text(lx, ly + 13 * i, line, size=11, anchor=anchor, fill=SOFT, style="italic")

    def legend(self, x, y):
        self.box(x, y, 16, 12, "", kind="app")
        self.text(x + 22, y + 10, "Application code", size=11, anchor="start", fill=SOFT)
        self.box(x + 130, y, 16, 12, "", kind="agent")
        self.text(x + 152, y + 10, "Agent", size=11, anchor="start", fill=SOFT)
        self.parts.append(
            f'<rect x="{x + 200}" y="{y}" width="22" height="12" rx="6" fill="#fff" stroke="{INK}" '
            'stroke-width="1.2" stroke-dasharray="5 3"/>'
        )
        self.text(x + 228, y + 10, "Fixed reply, turn ends", size=11, anchor="start", fill=SOFT)

    def save(self, name: str) -> None:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n<defs><marker id="a" viewBox="0 0 10 10" refX="9" '
            'refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 '
            f'L0,10 z" fill="{INK}"/></marker></defs>\n<rect width="{self.width}" height="{self.height}" fill="#fff"/>'
        )
        (OUT / f"{name}.svg").write_text(head + "\n" + "\n".join(self.parts) + "\n</svg>\n")


def input_boundary() -> None:
    f = Figure(1000, 740)
    f.legend(40, 20)
    steps = [
        ("1. Rate limit", ["apps/backend/rate_limit.py"], "11th message in a minute",
         "“Too many requests…”", ["No agent runs"]),
        ("2. Hidden-character removal", ["Strips invisible Unicode; visible words kept"], None, None, None),
        ("3. Privacy and credential check", ["Redacts emails and phone numbers"], "credential found",
         "“…blocked because it contains a credential.”", ["Blocked turn is not saved"]),
        ("4. English check", ["Skipped if step 6 would match"], "mostly not English",
         "“Linger can only read and reply in English…”", []),
        ("5. Injection rules", ["Adopted override and disclosure patterns"], "rule matches",
         "Fixed security decline", ["Reason is not revealed"]),
        ("6. Self-harm phrase match", ["First-person phrase; no model call"], "phrase matches",
         "Self-harm reply", ["Someone you trust, a doctor, a crisis line"]),
    ]
    x, w, h, pitch, y0 = 40, 360, 50, 74, 60
    f.box(x + 90, y0, 180, 36, "User's Line", kind="note")
    y = y0 + 36
    for i, (title, lines, cond, exit_title, exit_lines) in enumerate(steps):
        top = y0 + 60 + pitch * i
        f.arrow([(x + w / 2, y), (x + w / 2, top)])
        f.box(x, top, w, h, title, lines)
        if cond:
            f.arrow([(x + w, top + h / 2), (600, top + h / 2)], cond, at=(500, top + h / 2 - 7))
            f.box(600, top, 360, h, exit_title, exit_lines, kind="exit")
        y = top + h
    top = y0 + 60 + pitch * len(steps)
    f.arrow([(x + w / 2, y), (x + w / 2, top)])
    f.box(x, top, w, h + 6, "7. Emotional preflight", ["Provenance, no tools: continue_reflection", "or apply_boundary"], kind="agent")
    f.arrow([(x + w, top + h / 2), (600, top + h / 2)], "apply_boundary", at=(500, top + h / 2 - 7))
    f.box(600, top, 360, h + 6, "“That sounds deeply distressing…”",
          ["No search and no memory capture.", "A failed preflight gets a safe decline"], kind="exit")
    end = top + h + 6
    f.arrow([(x + w / 2, end), (x + w / 2, end + 34)], "continue_reflection", at=(x + w / 2 + 10, end + 22), anchor="start")
    f.box(x + 60, end + 34, 240, 44, "Muse: turn-triage", kind="agent")
    f.save("figure-3-input-boundary")


def visibility() -> None:
    cols = ["Current Line", "Earlier session text", "Book passages", "Account memories", "Web pages"]
    full, part, none = "full", "part", "none"
    rows = [
        ("Muse, triage", [(full, ""), (none, ""), (none, ""), (none, ""), (none, "")]),
        ("Muse, draft", [(full, ""), (part, "≤ 8 released turns,|16,000 characters"),
                         (part, "Only what|librarian_search returns"), (part, "Only as Serendipity|evidence"),
                         (part, "Only as Serendipity|evidence")]),
        ("Librarian", [(full, ""), (part, "User's own words,|never Muse's replies"),
                       (full, "Full work only for|private boundary inference"), (part, "Memories naming the|work, for inference"),
                       (none, "")]),
        ("Serendipity", [(full, "As its search cue"), (none, ""), (part, "Through Librarian,|within the boundary"),
                         (part, "search_memories,|no account identity"), (part, "When web policy|grants it")]),
        ("Provenance", [(full, ""), (part, "Verified exact|user statements only"), (part, "Frozen evidence|under review"),
                        (part, "Cited memories,|nomination, sources"), (part, "Cited pages|under review")]),
        ("Sculptor", [(none, ""), (none, ""), (none, "Offline chapter-cue|task only"),
                      (part, "2 to 12 records,|identity removed"), (none, "Offline research|task only")]),
    ]
    lw, cw, rh, top = 140, 166, 62, 70
    f = Figure(lw + cw * len(cols) + 30, top + rh * len(rows) + 80)
    for j, c in enumerate(cols):
        f.text(lw + cw * j + cw / 2, top - 14, c, weight="bold", size=12.5)
    for i, (name, cells) in enumerate(rows):
        y = top + rh * i
        fill = AGENT if i % 2 == 0 else "#f6f6f6"
        f.parts.append(f'<rect x="10" y="{y}" width="{lw + cw * len(cols) + 10}" height="{rh}" fill="{fill}"/>')
        f.text(20, y + rh / 2 + 4, name, weight="bold", anchor="start", size=12.5)
        for j, (level, note) in enumerate(cells):
            cx, cy = lw + cw * j + cw / 2, y + (20 if note else rh / 2)
            r = 7
            if level == full:
                f.parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{INK}"/>')
            elif level == part:
                f.parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="{INK}" stroke-width="1.4"/>')
                f.parts.append(f'<path d="M{cx},{cy - r} A{r},{r} 0 0 0 {cx},{cy + r} Z" fill="{INK}"/>')
            else:
                f.parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="#999" stroke-width="1.4"/>')
            for k, line in enumerate(note.split("|") if note else []):
                f.text(cx, cy + 22 + 13 * k, line, size=10.5, fill=SOFT)
    y = top + rh * len(rows) + 28
    f.parts.append(f'<circle cx="26" cy="{y - 4}" r="6" fill="{INK}"/>')
    f.text(38, y, "Sees all of it", size=11, anchor="start", fill=SOFT)
    f.parts.append(f'<circle cx="146" cy="{y - 4}" r="6" fill="#fff" stroke="{INK}" stroke-width="1.4"/>')
    f.parts.append(f'<path d="M146,{y - 10} A6,6 0 0 0 146,{y + 2} Z" fill="{INK}"/>')
    f.text(158, y, "Sees a bounded slice the application chooses", size=11, anchor="start", fill=SOFT)
    f.parts.append(f'<circle cx="436" cy="{y - 4}" r="6" fill="#fff" stroke="#999" stroke-width="1.4"/>')
    f.text(448, y, "Sees none of it", size=11, anchor="start", fill=SOFT)
    f.text(20, y + 26, "No agent writes storage or releases text. Only the application does both.",
           size=12, anchor="start", weight="bold")
    f.save("figure-3-agent-visibility")


def muse_turn() -> None:
    f = Figure(1000, 470)
    f.legend(20, 14)
    f.box(20, 60, 130, 70, "User's Line", kind="note")
    f.box(190, 60, 210, 70, "Step 1. Triage", ["Skill: turn-triage", "this Line only; no tools"], kind="agent")
    f.box(480, 60, 190, 70, "Tool grants", ["Application maps", "labels to tools"])
    f.box(750, 60, 230, 70, "Step 2. Draft", ["Skill: reflection", "bounded history + MuseTurn"], kind="agent")
    f.arrow([(150, 95), (190, 95)])
    f.arrow([(400, 95), (480, 95)], "three labels,\nno tool names", at=(440, 66))
    f.arrow([(670, 95), (750, 95)], "granted\ntools", at=(710, 66))
    f.box(720, 200, 260, 80, "Tool adapters", ["librarian_route · librarian_search", "serendipity_explore",
                                                 "Application adds exact words and scope"])
    f.arrow([(905, 130), (905, 200)], "id or\nintent only", at=(915, 158), anchor="start", both=True)
    f.box(720, 340, 120, 50, "Librarian", kind="agent")
    f.box(860, 340, 120, 50, "Serendipity", kind="agent")
    f.arrow([(780, 280), (780, 340)], both=True)
    f.arrow([(920, 280), (920, 340)], both=True)
    f.box(380, 200, 270, 80, "MuseCandidate", ["Reply · evidence declaration", "One memory nomination", "or a reason for none"])
    f.arrow([(770, 130), (770, 160), (515, 160), (515, 200)])
    f.box(380, 340, 270, 50, "Provenance review", ["Skill: candidate-review"], kind="agent")
    f.arrow([(515, 280), (515, 340)])
    f.box(40, 200, 260, 80, "Step 3. Revise", ["Skill: reflection, revision mode;", "rewrites flagged sentences only;",
                                                  "same tools as the draft"], kind="agent")
    f.arrow([(380, 365), (170, 365), (170, 280)], "revise, at most once", at=(275, 357))
    f.arrow([(300, 240), (380, 240)])
    f.text(515, 420, "Pass goes to the release checks. Reject, or no pass after the revision, ends in a safe decline.",
           size=11.5, fill=SOFT, style="italic")
    f.text(515, 445, "One agent, two skills. Muse can neither release its reply nor write memory.", size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-muse-turn")


def librarian() -> None:
    f = Figure(1000, 480)
    f.legend(20, 14)
    f.box(20, 60, 170, 70, "Book request", ["From librarian_route", "or librarian_search"], kind="note")
    f.box(230, 60, 210, 70, "Boundary confirmed?", ["Stated by the user, or", "saved for this account and book"])
    f.box(480, 60, 200, 70, "Infer ceiling", ["Skill: boundary-inference;", "private full-work candidates"], kind="agent")
    f.box(720, 50, 260, 95, "Application gate", ["Rejects a ceiling that rests on", "the Line alone, has confidence",
                                                     "below 0.75, or differs from its", "highest supporting chapter"])
    f.box(720, 185, 260, 70, "Identify stopping event", ["Skill: event-identification;", "must agree with the ceiling"], kind="agent")
    f.box(420, 190, 230, 60, "Which book and chapter", ["have you finished? No search"], kind="exit")
    f.arrow([(190, 95), (230, 95)])
    f.arrow([(440, 95), (480, 95)], "no", at=(460, 88))
    f.arrow([(680, 95), (720, 95)])
    f.arrow([(760, 145), (760, 165), (600, 165), (600, 190)], "rejected", at=(690, 160))
    f.arrow([(900, 145), (900, 185)], "passed", at=(910, 170), anchor="start")
    f.arrow([(720, 220), (650, 220)], "disagrees", at=(685, 212))
    f.arrow([(335, 130), (335, 300), (127, 300), (127, 340)], "yes", at=(345, 160), anchor="start")
    f.arrow([(850, 255), (850, 300), (335, 300)], "agrees: ceiling lasts this turn only", at=(600, 293))
    xs, w, y = (20, 268, 516, 764), 216, 340
    cards = [
        ("Plan request", ["Skill: book-request; spans", "copied exactly from user's words"], "agent"),
        ("Retrieval", ["Application; hybrid search", "opens only chapters ≤ boundary"], "app"),
        ("Judge evidence", ["Skill: evidence-assessment;", "retrieved records only, once each"], "agent"),
        ("Typed result to Muse", ["Ids looked up again; chapter grant", "from records; fixed strength sentence"], "app"),
    ]
    for i, (title, lines, kind) in enumerate(cards):
        f.box(xs[i], y, w, 80, title, lines, kind=kind)
        if i:
            f.arrow([(xs[i - 1] + w, y + 40), (xs[i], y + 40)])
    f.text(500, 455, "One agent, four skills. Text beyond the boundary never reaches the judge, Muse, the index, or the reranker.",
           size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-librarian")


def serendipity() -> None:
    f = Figure(1000, 545)
    f.legend(20, 14)
    f.box(20, 60, 200, 70, "serendipity_explore", ["Muse passes an intent;", "a pinned intent is checked"], kind="note")
    f.box(260, 60, 270, 70, "Build request scope", ["Active memories, confirmed reading,", "web policy; recall: memory only"])
    f.box(640, 67, 200, 56, "Decline", ["Agent not called"], kind="exit")
    f.arrow([(220, 95), (260, 95)])
    f.arrow([(530, 95), (640, 95)], "no permitted\nsource", at=(585, 80))
    f.box(10, 170, 735, 250, "Live skills", kind="panel")
    cards = [
        ("connection-discovery", ["Intent: find_connection or", "get_recommendation", "Searches books, memories, web",
                                  "Ranks candidates; a top-two", "tie produces a decline",
                                  "Returns ConnectionProposal", "or ConnectionDecline"]),
        ("source-gathering", ["Intent: gather_sources", "Collects every source the", "user named, side by side",
                              "Searches books, memories, web", "Does not rank or pick a winner",
                              "Returns SourceBundle", "or ConnectionDecline"]),
        ("memory-recall", ["Intent: recall_memory", "Searches memories only", "Finds the user's own",
                           "earlier words on the topic", "Returns MemoryRecall", "or ConnectionDecline"]),
    ]
    xs, w = (22, 262, 502), 228
    f.parts.append(f'<path d="M{xs[0] + w / 2},150 L{xs[2] + w / 2},150" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    f.parts.append(f'<path d="M395,130 L395,150" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    f.text(625, 147, "skill chosen by intent; each run is capped", size=11, anchor="start", fill=SOFT, style="italic")
    f.text(625, 161, "at 14 tool calls and 16 model requests", size=11, anchor="start", fill=SOFT, style="italic")
    f.parts.append(f'<path d="M{xs[0] + w / 2},440 L{xs[2] + w / 2},440" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    for x, (title, lines) in zip(xs, cards):
        f.arrow([(x + w / 2, 150), (x + w / 2, 205)])
        f.box(x, 205, w, 190, title, lines, kind="agent")
        f.parts.append(f'<path d="M{x + w / 2},395 L{x + w / 2},440" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    f.box(765, 170, 225, 250, "Offline only", kind="panel")
    f.box(777, 205, 201, 190, "self-review", ["No user and no tools", "Reads its own failed", "practice cases", "Proposes exact edits to",
                                               "connection-discovery", "Kept only if a rerun", "does better"], kind="agent")
    f.arrow([(300, 440), (300, 465)])
    f.box(150, 465, 300, 64, "Application recheck", ["Evidence within the grant; web pages", "opened in this run; ids in run ledger"])
    f.box(500, 465, 245, 64, "Back to Muse", ["Selected evidence only;", "one result cached per turn"])
    f.arrow([(450, 497), (500, 497)])
    f.save("figure-3-serendipity")


def provenance() -> None:
    f = Figure(1000, 600)
    f.legend(20, 14)
    f.text(20, 58, "One agent, three skills. Every run has no tools, no conversation history, and a fresh typed input.",
           weight="bold", anchor="start")
    cols = [
        ("Every turn, before Muse runs",
         ("Input", ["Current message", "Versioned emotional policy", "Nothing else"]),
         "emotional-preflight",
         ("Output", ["continue_reflection or", "apply_boundary; a self-harm", "phrase skips the model"]),
         ("Application then", ["Writes the boundary reply or", "lets Muse run; a failure ends", "in a safe decline"])),
        ("Every Muse draft and its revision",
         ("Input, ordered by trust", ["1. Application context and policy", "2. Canonical evidence",
                                      "3. Untrusted tool outcomes", "4. Untrusted candidate"]),
         "candidate-review",
         ("Three separate decisions", ["Response: pass, revise, or reject", "Capture: allow or veto",
                                       "Emotional boundary: apply or not"]),
         ("Application then", ["Validates the review, then", "rechecks quotes and ids", "before release"])),
        ("After each Sculptor proposal",
         ("Input", ["Sculptor's proposal", "Exact source memory snapshots", "The proposal digest"]),
         "curation-review",
         ("Output", ["allow, revise, or reject,", "echoing the proposal digest"]),
         ("Application then", ["Memory and Policy Service", "re-reads the sources and", "rejects a stale plan"])),
    ]
    xs, w = (20, 345, 670), 310
    for x, (when, (it, il), skill, (ot, ol), (tt, tl)) in zip(xs, cols):
        cx = x + w / 2
        f.box(x, 75, w, 44, when, kind="note")
        f.box(x, 145, w, 96, it, il, title_size=12)
        f.box(x, 267, w, 50, skill, kind="agent")
        f.box(x, 343, w, 80, ot, ol, title_size=12)
        f.box(x, 449, w, 72, tt, tl, title_size=12)
        for top, bottom in ((119, 145), (241, 267), (317, 343), (423, 449)):
            f.arrow([(cx, top), (cx, bottom)])
    f.text(500, 560, "In candidate review, a spoiler, prompt injection, policy override, harmful content, or instruction",
           size=11.5, fill=SOFT, style="italic")
    f.text(500, 578, "disclosure requires rejection, never revision.", size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-provenance")


def sculptor() -> None:
    f = Figure(1000, 470)
    f.legend(20, 14)
    f.text(20, 58, "One agent, five skills. Each skill only proposes; Provenance, the application, or a person decides.",
           weight="bold", anchor="start")
    f.box(10, 75, 980, 135, "After a memory capture (live)", kind="panel")
    f.box(25, 105, 270, 90, "memory-curation", ["The new record and up to 11 related", "ones; no account identity",
                                                 "Returns one action or no change"], kind="agent")
    f.box(345, 105, 230, 90, "Provenance review", ["Skill: curation-review;", "verdict echoes the digest"], kind="agent")
    f.box(625, 105, 350, 90, "Memory and Policy Service", ["Re-reads and re-hashes the sources;",
                                                            "rejects a stale plan; appends an audit",
                                                            "event; never edits the originals"])
    f.arrow([(295, 150), (345, 150)])
    f.arrow([(575, 150), (625, 150)], "allow", at=(600, 143))
    f.box(10, 235, 980, 215, "Offline only: no output reaches a user without human approval", kind="panel")
    cards = [
        ("memory-surfacing", ["Evaluation only", "Should stored memories be", "suggested now, later, or never?",
                              "Returns SurfaceNow, Defer,", "or DoNotSurface"]),
        ("chapter-cues", ["Revises each chapter's search", "aids so retrieval finds the", "chapter a user means",
                          "A person approves before", "search reads them"]),
        ("retrieval-error-analysis", ["Reads practice retrieval traces", "Groups first failures into", "counted categories",
                                      "Proposes no fix"]),
        ("retrieval-research", ["Web search and page reads", "Specifies one fix for the top", "approved failure category",
                                "A developer builds it", "(Experiment 4)"]),
    ]
    for i, (title, lines) in enumerate(cards):
        f.box(25 + 240 * i, 265, 225, 125, title, lines, kind="agent", title_size=12)
    f.text(500, 422, "Improvement loop: retrieval-error-analysis, then owner approves the categories, then retrieval-research,",
           size=11.5, fill=SOFT, style="italic")
    f.text(500, 439, "then owner approves the specification before a developer builds it.", size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-sculptor-skills")


def handoffs() -> None:
    f = Figure(1000, 470)
    f.legend(20, 14)
    f.box(390, 200, 220, 80, "Application", ["Builds every input and", "checks every output"])
    nodes = {
        "Muse": (60, 212, 180, "agent"), "Provenance": (760, 212, 180, "agent"),
        "Librarian": (200, 70, 180, "agent"), "Serendipity": (620, 70, 180, "agent"),
        "Sculptor": (200, 362, 180, "agent"),
    }
    for name, (x, y, w, kind) in nodes.items():
        f.box(x, y, w, 56, name, kind=kind)
    f.box(620, 362, 220, 56, "Memory and Policy Service")
    f.arrow([(390, 240), (240, 240)], "2, 3, 4, 6", at=(315, 232), both=True)
    f.arrow([(610, 240), (760, 240)], "1, 8, 10", at=(685, 232), both=True)
    f.arrow([(430, 200), (290, 126)], "4, 5, 7", at=(330, 170), anchor="end", both=True)
    f.arrow([(570, 200), (710, 126)], "6, 7", at=(670, 170), anchor="start", both=True)
    f.arrow([(430, 280), (290, 362)], "9", at=(325, 325), anchor="end", both=True)
    f.arrow([(570, 280), (730, 362)], "11, 12", at=(690, 318), anchor="start")
    f.text(500, 448, "No agent calls another directly. Numbers refer to the rows of the hand-off table.", size=11.5, fill=SOFT,
           style="italic")
    f.save("figure-3-handoffs")


def release() -> None:
    f = Figure(1020, 480)
    f.legend(20, 14)
    xs, w, y, h = (20, 222, 424, 626, 828), 172, 70, 86
    main = [
        ("MuseCandidate", ["Reply, declarations,", "nomination"], "note"),
        ("Candidate validator", ["Claimed spans are exact;", "evidence ids resolve"], "app"),
        ("Provenance review", ["Fresh input, no history"], "agent"),
        ("Release recheck", ["No leaked instructions;", "ids, locations, and quotes", "match reply and record"], "app"),
        ("Release to user", ["Only text that passed", "every check"], "app"),
    ]
    for i, (title, lines, kind) in enumerate(main):
        f.box(xs[i], y, w, h, title, lines, kind=kind)
        if i:
            f.arrow([(xs[i - 1] + w, y + h / 2), (xs[i], y + h / 2)], "pass" if i in (3, 4) else None,
                    at=((xs[i - 1] + w + xs[i]) / 2, y + h / 2 - 6))
    f.arrow([(xs[1] + 60, y), (xs[1] + 60, y - 18), (xs[0] + 110, y - 18), (xs[0] + 110, y)],
            "error: Muse repairs", at=(xs[1] - 15, y - 24))
    f.box(270, 215, 230, 66, "Muse revises", ["Flagged sentences only;", "at most once"], kind="agent")
    f.arrow([(464, y + h), (464, 215)], "revise", at=(456, 196), anchor="end")
    f.arrow([(270, 248), (250, 248), (250, y + h)])
    f.text(20, 320, "The revised draft is validated again,", size=11, anchor="start", fill=SOFT, style="italic")
    f.text(20, 334, "and the second review must resolve", size=11, anchor="start", fill=SOFT, style="italic")
    f.text(20, 348, "each earlier finding.", size=11, anchor="start", fill=SOFT, style="italic")
    f.box(480, 370, 300, 54, "Safe decline", ["Fixed text; reveals nothing; writes nothing"], kind="exit")
    f.arrow([(574, y + h), (574, 370)], "reject, or no pass\nafter the revision", at=(566, 320), anchor="end")
    f.arrow([(690, y + h), (690, 370)], "fail", at=(698, 320), anchor="start")
    f.box(800, 215, 200, 116, "Memory capture", ["Memory and Policy Service", "commits only if the turn was", "released, capture is on,",
                                                   "Provenance allowed it, and", "the span is exact, nonsensitive"])
    f.arrow([(xs[4] + w / 2, y + h), (xs[4] + w / 2, 215)], "if nominated", at=(xs[4] + w / 2 + 8, 190), anchor="start")
    f.text(460, 455, "A Provenance pass is necessary but never sufficient: the application rechecks before release.",
           size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-release")


if __name__ == "__main__":
    for make in (input_boundary, visibility, muse_turn, librarian, serendipity, provenance, sculptor, handoffs, release):
        make()
