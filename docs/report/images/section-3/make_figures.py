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
    f.box(x + 60, end + 34, 240, 44, "Muse (Section 3.2.1)", kind="agent")
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
    f.box(190, 60, 210, 70, "Step 1. Triage", ["Muse; this Line only", "no tools, no history"], kind="agent")
    f.box(480, 60, 190, 70, "Tool grants", ["Labels to tools", "(Table 3.2)"])
    f.box(750, 60, 230, 70, "Step 2. Draft", ["Muse; bounded history", "plus the typed MuseTurn"], kind="agent")
    f.arrow([(150, 95), (190, 95)])
    f.arrow([(400, 95), (480, 95)], "three labels,\nno tool names", at=(440, 66))
    f.arrow([(670, 95), (750, 95)], "granted\ntools", at=(710, 66))
    f.box(720, 200, 260, 80, "Tool adapters", ["librarian_route · librarian_search", "serendipity_explore",
                                                 "Application adds exact words and scope"])
    f.arrow([(905, 130), (905, 200)], "id or\nintent only", at=(915, 158), anchor="start", both=True)
    f.box(720, 340, 120, 50, "Librarian", ["Section 3.2.2"], kind="agent")
    f.box(860, 340, 120, 50, "Serendipity", ["Section 3.2.3"], kind="agent")
    f.arrow([(780, 280), (780, 340)], both=True)
    f.arrow([(920, 280), (920, 340)], both=True)
    f.box(380, 200, 270, 80, "MuseCandidate", ["Reply · evidence declaration", "One memory nomination", "or a reason for none"])
    f.arrow([(770, 130), (770, 160), (515, 160), (515, 200)])
    f.box(380, 340, 270, 50, "Provenance review", ["Section 3.4"], kind="agent")
    f.arrow([(515, 280), (515, 340)])
    f.box(40, 200, 260, 80, "Step 3. Revise", ["Muse rewrites flagged sentences;", "sentence labels keep the rest;",
                                                  "same tools as the draft"], kind="agent")
    f.arrow([(380, 365), (170, 365), (170, 280)], "revise, at most once", at=(275, 357))
    f.arrow([(300, 240), (380, 240)])
    f.text(515, 420, "Pass goes to the release checks. Reject, or no pass after the revision, ends in a safe decline.",
           size=11.5, fill=SOFT, style="italic")
    f.text(515, 445, "Muse can neither release its reply nor write memory.", size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-muse-turn")


def librarian() -> None:
    f = Figure(1000, 480)
    f.legend(20, 14)
    f.box(20, 60, 170, 70, "Book request", ["From librarian_route", "or librarian_search"], kind="note")
    f.box(230, 60, 210, 70, "Boundary confirmed?", ["Stated by the user, or", "saved for this account and book"])
    f.box(480, 60, 200, 70, "Infer ceiling", ["Librarian, private", "full-work candidates"], kind="agent")
    f.box(720, 50, 260, 95, "Application gate", ["Rejects a ceiling that rests on", "the Line alone, has confidence",
                                                     "below 0.75, or differs from its", "highest supporting chapter"])
    f.box(720, 185, 260, 70, "Identify stopping event", ["Librarian, separate run;", "must agree with the ceiling"], kind="agent")
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
        ("Plan request", ["Librarian; spans copied", "exactly from the user's words"], "agent"),
        ("Retrieval", ["Application; hybrid search", "opens only chapters ≤ boundary"], "app"),
        ("Judge evidence", ["Librarian; retrieved records only,", "each once, within budget"], "agent"),
        ("Typed result to Muse", ["Ids looked up again; chapter grant", "from records; fixed strength sentence"], "app"),
    ]
    for i, (title, lines, kind) in enumerate(cards):
        f.box(xs[i], y, w, 80, title, lines, kind=kind)
        if i:
            f.arrow([(xs[i - 1] + w, y + 40), (xs[i], y + 40)])
    f.text(500, 455, "Text beyond the boundary never reaches the judge, Muse, the index, or the reranker.",
           size=11.5, fill=SOFT, style="italic")
    f.save("figure-3-librarian")


def serendipity() -> None:
    f = Figure(1000, 450)
    f.legend(20, 14)
    f.box(20, 60, 200, 80, "serendipity_explore", ["Muse passes an intent only;", "a pinned intent is checked"], kind="note")
    f.box(250, 60, 240, 80, "Build request scope", ["Active memories, confirmed reading,", "web policy. Recall: memory only"])
    f.box(250, 200, 240, 56, "Decline", ["Agent not called"], kind="exit")
    f.arrow([(220, 100), (250, 100)])
    f.arrow([(370, 140), (370, 200)], "no permitted\nsource", at=(380, 162), anchor="start")
    f.box(520, 40, 460, 260, "Serendipity run: at most 14 tool calls and 16 model requests", kind="panel")
    f.arrow([(490, 100), (520, 100)])
    tx, tw = (535, 683, 831), 135
    tools = [("search_librarian", ["Book, via Librarian"]), ("search_memories", ["No account identity"]),
             ("Exa search, open", ["Only if web granted"])]
    steps = [("1. Search", ["granted sources"]), ("2. Drop", ["ineligible evidence"]), ("3. Rank", ["top-two tie: decline"])]
    for i in range(3):
        f.box(tx[i], 70, tw, 54, tools[i][0], tools[i][1], title_size=12)
        f.box(tx[i], 170, tw, 54, steps[i][0], steps[i][1], kind="agent", title_size=12)
        if i:
            f.arrow([(tx[i - 1] + tw, 197), (tx[i], 197)])
    bus = 147
    f.parts.append(f'<path d="M{tx[0] + tw / 2},170 L{tx[0] + tw / 2},{bus} L{tx[2] + tw / 2},{bus}" '
                   f'fill="none" stroke="{INK}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    for i in range(3):
        f.arrow([(tx[i] + tw / 2, bus), (tx[i] + tw / 2, 124)], dashed=True)
    f.text(750, 258, "Returns exactly one:", size=11.5, fill=SOFT)
    f.text(750, 278, "ConnectionProposal · MemoryRecall · ConnectionDecline", size=12, weight="bold")
    f.box(520, 340, 220, 76, "Application recheck", ["Evidence within the grant; web", "pages opened in this run"])
    f.box(770, 340, 210, 76, "Back to Muse", ["Selected evidence only;", "one result cached per turn"])
    f.arrow([(630, 300), (630, 340)])
    f.arrow([(740, 378), (770, 378)])
    f.text(250, 330, "Nothing is stored on the shared Agent", size=11.5, fill=SOFT, style="italic", anchor="start")
    f.text(250, 348, "between requests.", size=11.5, fill=SOFT, style="italic", anchor="start")
    f.save("figure-3-serendipity")


def provenance() -> None:
    f = Figure(1000, 470)
    f.legend(20, 14)
    f.text(20, 58, "ProvenanceInput, ordered by trust", weight="bold", anchor="start")
    layers = [
        ("Trusted application context", ["Policy, reading scope"], "app"),
        ("Canonical evidence", ["From application registries"], "app"),
        ("Untrusted tool outcomes", [], "exit"),
        ("Untrusted candidate", ["Muse's reply, declarations, nomination"], "exit"),
    ]
    for i, (title, lines, kind) in enumerate(layers):
        f.box(20, 70 + 54 * i, 290, 46, title, lines, kind=kind, title_size=12)
    f.box(370, 130, 210, 110, "Provenance", ["Candidate review", "no tools, no history,", "fresh input every run"], kind="agent")
    f.arrow([(310, 185), (370, 185)])
    outs = [
        ("Response: pass, revise, or reject", ["Spoiler, prompt injection, policy override, harmful",
                                               "content, or instruction disclosure: reject, never revise"]),
        ("Capture: allow or veto", ["Can veto a nomination; cannot authorise a write"]),
        ("Emotional boundary: apply or not", []),
    ]
    oy = (60, 150, 220)
    for i, (title, lines) in enumerate(outs):
        h = 74 if i == 0 else (56 if lines else 44)
        f.box(640, oy[i], 340, h, title, lines, title_size=12)
        f.arrow([(580, 185), (640, oy[i] + h / 2)])
    f.text(20, 330, "The same agent runs two other skills", weight="bold", anchor="start")
    f.box(20, 345, 300, 70, "Emotional preflight", ["Line and policy only:", "continue_reflection or apply_boundary"], kind="agent")
    f.box(345, 345, 300, 70, "Curation review", ["Sculptor's proposal and exact sources:", "verdict must echo the proposal digest"], kind="agent")
    f.box(680, 345, 300, 70, "Application validates", ["Review checked against its own input;", "a pass is necessary, never sufficient"])
    f.arrow([(810, 264), (830, 345)], "all three decisions", at=(826, 310), anchor="start")
    f.save("figure-3-provenance")


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
    for make in (input_boundary, visibility, muse_turn, librarian, serendipity, provenance, release):
        make()
