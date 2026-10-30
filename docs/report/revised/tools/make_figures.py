#!/usr/bin/env python3
"""Generate the revised group report's new diagrams as SVG files.

Run from the repository root, then render PNGs:

    python3 docs/report/revised/tools/make_figures.py
    node docs/report/revised/tools/render_svgs.mjs

Every diagram shares one visual language: grey boxes are model-backed agents,
white boxes are deterministic application code, dark boxes are the reader's
input and output, and dashed boxes are fixed replies or optional services.
The chat-turn strip (Figure 3.8) is the base for Figures 6.1, 7.1 and 10.1, so
step numbers mean the same thing in every figure.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "figures"

FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
INK = "#1f1f1f"
MUTED = "#5a5a5a"
FAINT = "#9a9a9a"
AGENT = "#e4e4e4"
SEC = "#b4442c"
SEC_FILL = "#f9e6df"
STOP = "#b23a2a"
DECISION = "#f4efe3"

STYLES = {
    # kind: (fill, stroke, dash, text colour, sub colour)
    "code": ("#ffffff", INK, None, INK, MUTED),
    "agent": (AGENT, INK, None, INK, "#444"),
    "term": ("#232323", "#232323", None, "#ffffff", "#d0d0d0"),
    "fixed": ("#ffffff", INK, "5 4", INK, MUTED),
    "ext": ("#ffffff", "#6b6b6b", "5 4", INK, MUTED),
    "muted": ("#f6f6f6", "#b9b9b9", None, "#3a3a3a", MUTED),
    "decision": (DECISION, INK, None, INK, MUTED),
    "stop": (STOP, STOP, None, "#ffffff", "#f6d9d4"),
    "note": ("#ffffff", "#9a9a9a", "4 4", "#3a3a3a", MUTED),
    "sec": (SEC_FILL, SEC, None, INK, MUTED),
}


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.parts: list[str] = []

    def add(self, part: str) -> None:
        self.parts.append(part)

    def render(self) -> str:
        markers = "".join(
            f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
            for name, colour in (("ink", INK), ("muted", "#777777"), ("sec", SEC), ("stop", STOP))
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
            f'font-family="{escape(FONT)}">'
            f"<defs>{markers}</defs>"
            f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>'
            + "".join(self.parts)
            + "</svg>\n"
        )

    # Primitives -----------------------------------------------------------

    def text(
        self,
        x: float,
        y: float,
        content: str,
        size: float = 12,
        weight: int = 400,
        fill: str = INK,
        anchor: str = "middle",
        italic: bool = False,
        bg: bool = False,
    ) -> None:
        if bg:
            width = len(content) * size * 0.56 + 8
            left = {"middle": x - width / 2, "start": x - 4, "end": x - width + 4}[anchor]
            self.add(
                f'<rect x="{left:.1f}" y="{y - size * 0.95:.1f}" width="{width:.1f}" '
                f'height="{size * 1.3:.1f}" fill="#ffffff"/>'
            )
        style = ' font-style="italic"' if italic else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{style}>{escape(content)}</text>'
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str,
        stroke: str = "none",
        width: float = 1.4,
        dash: str | None = None,
        rx: float = 6,
    ) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'
        )

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        kind: str = "code",
        title: list[str] | str = (),
        lines: list[str] | tuple[str, ...] = (),
        number: str | None = None,
        title_size: float = 13.5,
        line_size: float = 11.5,
        outline: str | None = None,
    ) -> tuple[float, float, float, float]:
        fill, stroke, dash, colour, sub = STYLES[kind]
        self.rect(x, y, w, h, fill, stroke, 1.4, dash)
        if outline:
            self.rect(x - 3, y - 3, w + 6, h + 6, "none", outline, 2.4, None, rx=8)
        titles = [title] if isinstance(title, str) else list(title)
        blocks: list[tuple[str, float, int, str]] = []
        if number:
            blocks.append((number, 11, 600, FAINT if kind != "term" else "#bdbdbd"))
        blocks += [(t, title_size, 650, colour) for t in titles]
        blocks += [(t, line_size, 400, sub) for t in lines]
        heights = [size * (1.22 if weight >= 600 else 1.32) for _, size, weight, _ in blocks]
        gap = 3 if lines and titles else 0
        total = sum(heights) + gap
        cursor = y + (h - total) / 2
        for index, ((content, size, weight, fill_colour), height) in enumerate(zip(blocks, heights)):
            if index == len(blocks) - len(lines) and lines and titles:
                cursor += gap
            self.text(x + w / 2, cursor + size * 0.92, content, size, weight, fill_colour)
            cursor += height
        return (x, y, w, h)

    def line(
        self,
        points: list[tuple[float, float]],
        arrow: bool = True,
        dashed: bool = False,
        colour: str = "ink",
        width: float = 1.4,
        both: bool = False,
    ) -> None:
        stroke = {"ink": INK, "muted": "#777777", "sec": SEC, "stop": STOP}[colour]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        dash_attr = ' stroke-dasharray="6 4"' if dashed else ""
        end = f' marker-end="url(#arr-{colour})"' if arrow else ""
        start = f' marker-start="url(#arr-{colour})"' if both else ""
        self.add(
            f'<polyline points="{path}" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}"{dash_attr}{end}{start}/>'
        )

    def badge(self, cx: float, cy: float, label: str, colour: str = SEC) -> None:
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11.5" fill="{colour}"/>')
        self.text(cx, cy + 4.3, label, 12, 700, "#ffffff")

    def bar(self, x1: float, x2: float, y: float, colour: str, dashed: bool = False) -> None:
        dash_attr = ' stroke-dasharray="7 5"' if dashed else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'stroke="{colour}" stroke-width="4"{dash_attr}/>'
        )

    def legend(self, x: float, y: float, items: list[tuple[str, str]]) -> None:
        """Draw legend swatches. Kinds use STYLES; 'arrow'/'dashed-arrow'/'outline' are special."""
        cursor = x
        for kind, label in items:
            if kind == "arrow":
                self.line([(cursor, y), (cursor + 34, y)])
                cursor += 42
            elif kind == "dashed-arrow":
                self.line([(cursor, y), (cursor + 34, y)], dashed=True)
                cursor += 42
            elif kind == "outline":
                self.rect(cursor, y - 8, 26, 16, "#ffffff", SEC, 2.4, None, rx=4)
                cursor += 34
            else:
                fill, stroke, dash, _, _ = STYLES[kind]
                self.rect(cursor, y - 8, 26, 16, fill, stroke, 1.3, dash, rx=4)
                cursor += 34
            self.text(cursor, y + 4.5, label, 12, 400, "#333333", "start")
            cursor += len(label) * 6.9 + 30


# Shared chat-turn strip -------------------------------------------------------

TURN_STEPS = [
    ("1", ["Reader's", "Line"], [], "term"),
    ("2", ["Pre-model", "checks"], ["six checks"], "code"),
    ("3", ["Emotional", "preflight"], ["Provenance"], "agent"),
    ("4", ["Triage, then", "tool grants"], ["Muse"], "agent"),
    ("5", ["Tool calls"], ["Librarian,", "Serendipity"], "agent"),
    ("6", ["Draft with", "evidence"], ["Muse"], "agent"),
    ("7", ["Candidate", "review"], ["Provenance"], "agent"),
    ("8", ["Release", "checks"], ["quotes, ids,", "scope"], "code"),
    ("9", ["Memory", "commit"], ["if allowed"], "code"),
    ("10", ["Reply"], [], "term"),
]


def turn_strip(
    svg: Svg,
    x0: float,
    y0: float,
    width: float,
    height: float,
    gap: float,
    outlines: dict[str, str] | None = None,
) -> dict[str, tuple[float, float, float, float]]:
    boxes = {}
    for index, (number, title, lines, kind) in enumerate(TURN_STEPS):
        x = x0 + index * (width + gap)
        boxes[number] = svg.box(
            x,
            y0,
            width,
            height,
            kind,
            title,
            lines,
            number=number,
            outline=(outlines or {}).get(number),
        )
        if index:
            svg.line([(x - gap + 1, y0 + height / 2), (x - 1, y0 + height / 2)], width=1.2)
    return boxes


def centre(b: tuple[float, float, float, float]) -> float:
    return b[0] + b[2] / 2


# Figure 3.8: the harness strip ------------------------------------------------


def figure_turn_strip() -> Svg:
    svg = Svg(1400, 330)
    svg.text(
        40,
        30,
        "One chat turn, numbered as in Figure 2.2. Grey steps are agents; white steps are application code.",
        13,
        400,
        MUTED,
        "start",
    )
    steps = turn_strip(svg, 40, 50, 116, 118, 16)

    def span(first: str, last: str, row_y: float, colour: str, head: str, sub: str, dashed=False):
        x1, x2 = steps[first][0], steps[last][0] + steps[last][2]
        svg.bar(x1, x2, row_y, colour, dashed)
        mid = (x1 + x2) / 2
        svg.text(mid, row_y + 23, head, 13.5, 700, colour)
        svg.text(mid, row_y + 41, sub, 12, 400, MUTED)

    span("2", "3", 196, "#c0532f", "3.2.1 Input checks", "what reaches an agent")
    span("5", "7", 196, "#2c5a8c", "3.2.3 Context and hand-offs", "what an agent sees and passes on")
    span("9", "9", 196, "#a0701c", "3.2.5 Memory writes", "what is kept")
    span("4", "5", 266, "#1f7a6c", "3.2.2 Tasks and tools", "what an agent may do")
    span("7", "8", 266, "#7c4aa8", "3.2.4 Release checks", "what reaches the user")
    span("9", "10", 266, "#8a8a8a", "3.2.6 Self-improvement loop", "offline, outside the turn", dashed=True)
    return svg


# Figure 6.1: security checkpoints on the same strip ---------------------------


def figure_security_checkpoints() -> Svg:
    svg = Svg(1400, 420)
    svg.text(
        40,
        24,
        "The chat turn from Figure 3.8. Red outlines mark the six runtime security checkpoints in Table 6.3.",
        13,
        400,
        MUTED,
        "start",
    )
    outlined = {n: SEC for n in ("2", "4", "5", "7", "8", "9")}
    steps = turn_strip(svg, 40, 62, 116, 118, 16, outlines=outlined)

    top = 62 - 4
    svg.badge(centre(steps["2"]), top, "1")
    svg.badge(centre(steps["4"]), top, "2")
    svg.badge((centre(steps["7"]) + centre(steps["8"])) / 2, top, "5")
    svg.badge(centre(steps["9"]), top, "6")

    label_y = 214

    def checkpoint_label(x: float, head: str, risks: str) -> None:
        svg.text(x, label_y, head, 13, 700, SEC)
        svg.text(x, label_y + 18, risks, 12, 400, MUTED)

    checkpoint_label(centre(steps["2"]), "Input checks", "R1, R11")
    checkpoint_label(centre(steps["4"]), "Grants and hand-offs", "R1, R8")
    pair_mid = (centre(steps["7"]) + centre(steps["8"])) / 2
    checkpoint_label(pair_mid, "Review and release", "R1, R2, R3, R8")
    checkpoint_label(centre(steps["9"]), "Memory write", "R5, R6, R7")

    # Step 5 holds two checkpoints, drawn as sub-steps.
    s5 = steps["5"]
    sub_y, sub_w, sub_h, sub_gap = 270, 170, 92, 22
    span_mid = centre(s5) + 66
    left_x = span_mid - sub_w - sub_gap / 2
    right_x = span_mid + sub_gap / 2
    svg.line([(centre(s5), s5[1] + s5[3] + 4), (centre(s5), 246)], arrow=False, dashed=True, colour="muted")
    svg.line([(left_x + sub_w / 2, 246), (right_x + sub_w / 2, 246)], arrow=False, dashed=True, colour="muted")
    svg.line([(left_x + sub_w / 2, 246), (left_x + sub_w / 2, sub_y - 2)], dashed=True, colour="muted")
    svg.line([(right_x + sub_w / 2, 246), (right_x + sub_w / 2, sub_y - 2)], dashed=True, colour="muted")
    svg.text(centre(s5) - 8, 240, "inside step 5", 11.5, 400, MUTED, "end", italic=True)
    svg.box(left_x, sub_y, sub_w, sub_h, "code", "Web privacy gate", ["Serendipity's web tool", "R4"], outline=SEC)
    svg.box(right_x, sub_y, sub_w, sub_h, "code", "Retrieval cap", ["chapter ceiling on book", "evidence · R3"], outline=SEC)
    svg.badge(left_x + 2, sub_y - 2, "3")
    svg.badge(right_x + 2, sub_y - 2, "4")

    svg.legend(40, 398, [("agent", "model-backed agent"), ("code", "application code"), ("outline", "security checkpoint"), ("term", "reader's input and output")])
    return svg


# Figure 7.1: test coverage over the turn ---------------------------------------

COVERAGE_COLUMNS = [
    ("", ["Browser UI,", "HTTP API"], ["before step 1"], "muted"),
    ("2", ["Pre-model", "checks"], [], "code"),
    ("3", ["Emotional", "preflight"], [], "agent"),
    ("4", ["Triage"], [], "agent"),
    ("5", ["Tool calls"], [], "agent"),
    ("6", ["Draft"], [], "agent"),
    ("7", ["Candidate", "review"], [], "agent"),
    ("8", ["Release", "checks"], [], "code"),
    ("9", ["Memory", "commit"], [], "code"),
    ("", ["Curation"], ["Sculptor,", "after step 9"], "agent"),
]

MODEL_KINDS = {
    "none": ("#ffffff", "#8a8a8a", "4 3", "#333333"),
    "stub": ("#dce8f5", "#9fbad8", None, "#1f3550"),
    "local": ("#8fb3d6", "#6d97c2", None, "#10243a"),
    "live": ("#2b4f78", "#2b4f78", None, "#ffffff"),
}

COVERAGE_ROWS = [
    ("Automated in CI", None),
    ("Frontend component tests", ("Vitest, 127 tests", [(0, 0, "components", "none")])),
    ("Playwright browser tests", ("Chromium, 3 journeys", [(0, 0, "APIs mocked", "none")])),
    ("Container checks", ("offline image", [(0, 0, "ready, auth", "none"), (8, 8, "restart", "none")])),
    (
        "Unit and contract tests",
        ("backend, 4,634 tests", [(0, 9, "authority boundaries, validators, release blockers, storage rules", "stub")]),
    ),
    ("Retrieval regression tests", ("separate job, 7 tests", [(4, 4, "ranking", "local")])),
    ("Manual or release-gated", None),
    (
        "Component evaluations",
        (
            "one agent at a time (App. A)",
            [
                (2, 2, "preflight", "live"),
                (3, 3, "triage", "live"),
                (4, 4, "each alone", "live"),
                (5, 5, "reflection", "live"),
                (6, 6, "draft review", "live"),
            ],
        ),
    ),
    (
        "Scenario replay",
        ("16 Scenarios, 79 Scenes", [(1, 8, "production chat-turn runner; human-adopted Ground truth", "live"), (9, 9, "curation", "live")]),
    ),
    ("Release behavioural suite", ("6 Scenarios, 22 Scenes", [(0, 8, "replay and live HTTP smoke, 29 October 2026", "live")])),
    ("HTTP load tests", ("five retained runs", [(0, 8, "streamed turns, up to five readers; Sculptor not run", "live")])),
]


def figure_test_coverage() -> Svg:
    col_x0, col_w, col_gap = 262, 108, 6
    width = col_x0 + len(COVERAGE_COLUMNS) * (col_w + col_gap) + 14
    svg = Svg(width, 640)
    svg.text(
        20,
        24,
        "Columns follow the chat turn in Figure 3.8. Each bar shows where a test acts and which kind of model it uses.",
        13,
        400,
        MUTED,
        "start",
    )
    header_y, header_h = 40, 76
    body_top, body_bottom = header_y + header_h + 6, 576
    columns = []
    for index, (number, title, lines, kind) in enumerate(COVERAGE_COLUMNS):
        x = col_x0 + index * (col_w + col_gap)
        columns.append(x)
        stripe = "#f3f3f3" if kind == "agent" else "#fbfbfb"
        svg.rect(x, body_top, col_w, body_bottom - body_top, stripe, "#e2e2e2", 1, None, rx=0)
        svg.box(x, header_y, col_w, header_h, kind, title, lines, number=number or None, title_size=12.5, line_size=10.5)

    y = body_top + 6
    for name, detail in COVERAGE_ROWS:
        if detail is None:
            svg.rect(14, y, width - 28, 26, "#ececec", rx=3)
            svg.text(24, y + 18, name, 13, 700, "#333333", "start")
            y += 34
            continue
        sub, chips = detail
        svg.text(22, y + 16, name, 13, 650, INK, "start")
        svg.text(22, y + 32, sub, 11.5, 400, MUTED, "start")
        for first, last, label, model in chips:
            fill, stroke, dash, text_colour = MODEL_KINDS[model]
            x1 = columns[first] + 4
            x2 = columns[last] + col_w - 4
            svg.rect(x1, y + 4, x2 - x1, 30, fill, stroke, 1.2, dash, rx=5)
            svg.text((x1 + x2) / 2, y + 23.5, label, 11.5, 500, text_colour)
        y += 44

    lx = 22
    svg.text(lx, 612, "Model used:", 12.5, 650, INK, "start")
    lx += 92
    for model, label in (("none", "no model"), ("stub", "stubbed model"), ("local", "local embedder, reranker"), ("live", "live hosted model")):
        fill, stroke, dash, _ = MODEL_KINDS[model]
        svg.rect(lx, 600, 30, 18, fill, stroke, 1.2, dash, rx=4)
        svg.text(lx + 38, 613, label, 12, 400, "#333333", "start")
        lx += 38 + len(label) * 6.9 + 34
    return svg


# Figure 10.1: where answers were lost ------------------------------------------


def figure_evidence_loss() -> Svg:
    svg = Svg(1400, 470)
    steps = [
        ("2", ["Pre-model", "checks"], [], "code", "1"),
        ("3", ["Emotional", "preflight"], ["Provenance"], "agent", None),
        ("4", ["Triage"], ["Muse"], "agent", "1"),
        ("5a", ["Reading", "position"], ["Librarian"], "agent", "1"),
        ("5b", ["Request", "plan"], ["Librarian"], "agent", "2"),
        ("5c", ["Search"], ["books or notes"], "code", "3"),
        ("6", ["Draft"], ["Muse"], "agent", None),
        ("7", ["Candidate", "review"], ["Provenance"], "agent", "4"),
    ]
    x0, w, h, gap, y0 = 40, 142, 98, 22, 108
    boxes = {}
    region_right = x0 + 6 * (w + gap) - gap / 2 - 4
    svg.rect(24, 40, region_right - 24, 380, "#fbeee8", rx=10)
    svg.text(40, 72, "Before drafting: 8 of the 9 Scenes were lost here", 15, 700, "#a8401f", "start")
    svg.text(region_right + 26, 72, "After drafting: 1", 15, 700, "#555555", "start")
    for index, (number, title, lines, kind, problem) in enumerate(steps):
        x = x0 + index * (w + gap)
        boxes[number] = svg.box(x, y0, w, h, kind, title, lines, number=number)
        if index:
            svg.line([(x - gap + 1, y0 + h / 2), (x - 1, y0 + h / 2)], width=1.2)
        if problem:
            colour = SEC if problem != "4" else "#666666"
            svg.badge(x + w / 2, y0 - 2, problem, colour)

    def problem(first: str, last: str, colour: str, head: str, body: list[str], count: str) -> None:
        x1, x2 = boxes[first][0], boxes[last][0] + boxes[last][2]
        svg.bar(x1, x2, 232, colour)
        svg.text(x1, 264, head, 15, 700, colour, "start")
        for i, row in enumerate(body):
            svg.text(x1, 288 + i * 19, row, 12.5, 400, "#333333", "start")
        svg.text(x1, 386, count, 13.5, 700, colour, "start")

    problem("2", "5a", "#a8401f", "Whole-turn fallback", [
        "One failed check replaces the whole turn with a refusal,",
        "a clarifying question or fewer tools. The legitimate part",
        "of the request is discarded with it.",
    ], "4 Scenes")
    problem("5b", "5b", "#a8401f", "Incomplete plan", ["Part of the request", "is never searched."], "2 Scenes")
    problem("5c", "5c", "#a8401f", "Word matching", ["A note worded", "differently from the", "question is not found."], "2 Scenes")
    problem("7", "7", "#666666", "Over-refusal", ["A correct question", "is refused", "(Learning 3)."], "1 Scene")
    svg.text(
        24,
        448,
        "Final run, 16 October 2026. Each Scene gave the reader a safe reply that missed what they asked for. "
        "Step numbers follow Figure 3.8; 5a to 5c are parts of step 5.",
        12,
        400,
        MUTED,
        "start",
        italic=True,
    )
    return svg


# Figure 10.3: Provenance verdicts -------------------------------------------------


def figure_provenance_verdicts() -> Svg:
    svg = Svg(1300, 440)
    left, top, cell_w, cell_h, gap = 230, 60, 500, 132, 16
    col2 = left + cell_w + gap
    row2 = top + cell_h + gap
    svg.text(left + cell_w / 2, 44, "Provenance passed it", 15, 700)
    svg.text(col2 + cell_w / 2, 44, "Provenance sent it back", 15, 700)
    for y, word in ((top, "right"), (row2, "wrong")):
        svg.text(30, y + cell_h / 2 - 4, "Muse's draft", 12.5, 400, MUTED, "start")
        svg.text(30, y + cell_h / 2 + 18, f"was {word}", 16, 700, INK, "start")

    def cell(x, y, fill, stroke, head, head_colour, rows):
        svg.rect(x, y, cell_w, cell_h, fill, stroke, 2 if stroke != "none" else 1, None, rx=8)
        svg.text(x + 24, y + 36, head, 17, 700, head_colour, "start")
        for i, row in enumerate(rows):
            svg.text(x + 24, y + 66 + i * 22, row, 13.5, 400, "#2a2a2a", "start")

    cell(left, top, "#f4f3f0", "none", "Correct pass", "#555555", ["Test suite: passed 0.88 of safe drafts"])
    cell(col2, top, "#fcefe0", "#d9822b", "Over-refusal", "#b15d12", [
        "Test suite: sent back 0.12 of safe drafts",
        "Final run: refused a correct question",
    ])
    cell(left, row2, "#fbe4e2", "#c0392b", "Missed error", "#a52a1e", [
        "Test suite: passed 0.06 of unsafe drafts",
        "Final run: “the Dodo takes the thimble”",
    ])
    cell(col2, row2, "#f4f3f0", "none", "Correct catch", "#555555", [
        "Test suite: blocked 0.94 of unsafe drafts",
        "Example: an unsupported claim (Figure 3.6)",
    ])

    # Added error: a false finding on a right draft, then a wrong revision passes.
    start_x, start_y = col2 + cell_w, top + cell_h / 2
    lane_x, lane_y = col2 + cell_w + 34, row2 + cell_h + 26
    end_x = left + cell_w / 2
    svg.line(
        [(start_x + 2, start_y), (lane_x, start_y), (lane_x, lane_y), (end_x, lane_y), (end_x, row2 + cell_h + 3)],
        dashed=True,
        colour="sec",
        width=1.8,
    )
    svg.text(end_x + 16, lane_y + 26, "Added error: the first review flags a correct draft, Muse's revision introduces the error,", 13.5, 650, SEC, "start")
    svg.text(end_x + 16, lane_y + 46, "and the second review passes it (development run: a Pinocchio line given to Lamp-Wick).", 13.5, 400, SEC, "start")
    return svg


# Figure 10.4: worked examples ----------------------------------------------------


def figure_provenance_examples() -> Svg:
    svg = Svg(1400, 560)
    cols = [(210, "Source"), (520, "Muse's draft"), (830, "Provenance"), (1120, "What the reader got")]
    col_w = [270, 270, 250, 250]
    for (x, head), w in zip(cols, col_w):
        svg.text(x, 32, head, 14, 650, "#666666", "start")
    svg.add('<line x1="20" y1="46" x2="1380" y2="46" stroke="#cccccc" stroke-width="1.2"/>')

    rows = [
        (
            "Missed error",
            "final run",
            "#a52a1e",
            ("Alice's Adventures in Wonderland", ["“Hand it over here,”", "said the Dodo."]),
            (["“The Dodo takes the", "thimble from her pocket.”"], "Wrong"),
            ["Passed it"],
            ("A wrong detail", "in the reply", "#fbe4e2", "#a52a1e"),
        ),
        (
            "Added error",
            "development run",
            "#a52a1e",
            ("The Adventures of Pinocchio", ["Pinocchio: “one hour more", "or less makes very little", "difference.”"]),
            (["Gives the line", "to Pinocchio"], "Right"),
            ["Flagged the speaker;", "Muse's revision gave the", "line to Lamp-Wick; the", "second review passed it"],
            ("A wrong speaker", "in the reply", "#fbe4e2", "#a52a1e"),
        ),
        (
            "Over-refusal",
            "final run",
            "#b15d12",
            ("Reader's message", ["“…finished two days before", "the assembly. Which day", "does that make my deadline?”"]),
            (["“What day is", "the assembly?”"], "Right"),
            ["Sent it back", "as out of scope"],
            ("A refusal instead", "of the question", "#fcefe0", "#b15d12"),
        ),
    ]
    y = 64
    row_h = 150
    for name, run, colour, source, draft, verdict, outcome in rows:
        svg.text(24, y + row_h / 2 - 6, name, 17, 700, colour, "start")
        svg.text(24, y + row_h / 2 + 15, run.capitalize(), 12.5, 400, MUTED, "start")
        # Source
        sx, sw, bh = cols[0][0], col_w[0], row_h - 26
        svg.rect(sx, y, sw, bh, "#ffffff", "#c8c8c8", 1.2)
        svg.text(sx + 16, y + 24, source[0], 12, 400, "#777777", "start", italic=True)
        for i, row in enumerate(source[1]):
            svg.text(sx + 16, y + 50 + i * 21, row, 14, 400, INK, "start")
        # Draft
        dx, dw = cols[1][0], col_w[1]
        wrong = draft[1] == "Wrong"
        svg.rect(dx, y, dw, bh, "#fbe4e2" if wrong else "#e8f3ea", "#c0392b" if wrong else "#3d8a52", 1.4)
        for i, row in enumerate(draft[0]):
            svg.text(dx + 16, y + 34 + i * 22, row, 14, 400, INK, "start")
        pill_colour = "#c0392b" if wrong else "#2f7a46"
        svg.rect(dx + 16, y + bh - 38, 64, 24, pill_colour, rx=12)
        svg.text(dx + 48, y + bh - 21.5, draft[1], 12, 650, "#ffffff")
        # Provenance verdict
        px, pw = cols[2][0], col_w[2]
        svg.rect(px, y, pw, bh, "#f2f1ee", INK, 1.4)
        start = y + bh / 2 - (len(verdict) - 1) * 10.5 + 5
        for i, row in enumerate(verdict):
            svg.text(px + pw / 2, start + i * 21, row, 14, 650, INK)
        # Outcome
        ox, ow = cols[3][0], col_w[3]
        svg.rect(ox, y, ow, bh, outcome[2], "none", rx=6)
        svg.text(ox + 18, y + bh / 2 - 4, outcome[0], 14.5, 700, outcome[3], "start")
        svg.text(ox + 18, y + bh / 2 + 18, outcome[1], 14, 400, INK, "start")
        for a, b in ((sx + sw, dx), (dx + dw, px), (px + pw, ox)):
            svg.line([(a + 4, y + bh / 2), (b - 4, y + bh / 2)])
        y += row_h + 16
    return svg


# Figure 2.1: logical architecture -----------------------------------------------


def figure_logical_architecture() -> Svg:
    svg = Svg(1400, 900)

    def band(y, h, label, bottom=False):
        svg.rect(14, y, 1372, h, "#f6f6f6", "#d8d8d8", 1, None, rx=4)
        svg.text(28, y + h - 8 if bottom else y + 20, label, 12, 700, "#666666", "start")

    band(14, 110, "PRESENTATION AND TRANSPORT")
    band(140, 250, "APPLICATION LAYER (deterministic code)")
    band(430, 236, "AGENT LAYER (model-backed)", bottom=True)
    band(700, 140, "SERVICES AND STORES (deterministic)")

    react = svg.box(40, 44, 300, 64, "code", "React web client", ["chat, live agent map, Inspect, Library"])
    api = svg.box(550, 44, 300, 64, "code", "FastAPI adapter", ["bearer tokens, rate limit, SSE stream"])
    sqlite = svg.box(1060, 44, 300, 64, "code", "SQLite", ["accounts, transcripts, reading progress"])
    svg.line([(340, 76), (548, 76)])
    svg.text(444, 68, "HTTP, SSE", 11.5, 400, MUTED, italic=True)
    svg.line([(850, 76), (1058, 76)])
    svg.text(954, 68, "accounts, transcripts", 11.5, 400, MUTED, italic=True)

    turn = svg.box(550, 170, 300, 62, "code", "run_chat_turn", ["stage order, release, capture"])
    svg.line([(700, 108), (700, 168)])
    svg.text(708, 142, "one turn per request", 11.5, 400, MUTED, "start", italic=True)

    comps = [
        ("Input guards", ["before any agent runs"]),
        ("Runtime skill selection", ["13 chat skills, typed contracts"]),
        ("Granted tools", ["set by code from triage"]),
        ("Evidence index", ["request-scoped"]),
        ("Release checks", ["quotes, citations, scope"]),
        ("Memory and Policy Service", ["sole writer of memories", "and curation"]),
    ]
    comp_w, comp_gap, comp_y = 208, 18, 300
    comp_x0 = 40
    bus_y = 268
    svg.line([(700, 232), (700, bus_y)], arrow=False)
    xs = []
    for index, (title, lines) in enumerate(comps):
        x = comp_x0 + index * (comp_w + comp_gap)
        xs.append(x)
        svg.box(x, comp_y, comp_w, 70, "code", title, lines, title_size=13)
    svg.line([(xs[0] + comp_w / 2, bus_y), (xs[-1] + comp_w / 2, bus_y)], arrow=False)
    for x in xs:
        svg.line([(x + comp_w / 2, bus_y), (x + comp_w / 2, comp_y - 2)])

    agents = [
        ("Provenance", ["emotional preflight", "candidate review", "curation review"], "no tools; reads frozen evidence"),
        ("Muse", ["turn triage", "reflection (draft, revision)"], "calls tools only through the application"),
        ("Librarian", ["boundary inference", "event identification", "book request", "evidence assessment"], "judges retrieved records only"),
        ("Serendipity", ["connection discovery", "source gathering", "memory recall"], "searches what its grant allows"),
        ("Sculptor", ["memory curation"], "sees records, not the account"),
    ]
    agent_w, agent_gap, agent_y, agent_h = 252, 18, 470, 168
    agent_boxes = []
    task_bus = 410
    skill_x = xs[1] + comp_w / 2
    svg.line([(skill_x, comp_y + 70), (skill_x, task_bus)], arrow=False)
    for index, (name, skills, note) in enumerate(agents):
        x = 32 + index * (agent_w + agent_gap)
        agent_boxes.append((x, agent_y, agent_w, agent_h))
        svg.rect(x, agent_y, agent_w, agent_h, AGENT, INK, 1.4)
        svg.text(x + agent_w / 2, agent_y + 28, name, 15, 700)
        svg.add(
            f'<line x1="{x + 18}" y1="{agent_y + 40}" x2="{x + agent_w - 18}" y2="{agent_y + 40}" '
            f'stroke="#9a9a9a" stroke-width="1"/>'
        )
        for i, skill in enumerate(skills):
            svg.text(x + agent_w / 2, agent_y + 62 + i * 18, skill, 12.5, 400, "#333333")
        svg.text(x + agent_w / 2, agent_y + agent_h - 14, note, 11.5, 400, "#555555", italic=True)
        svg.line([(x + agent_w / 2, task_bus), (x + agent_w / 2, agent_y - 2)])
    first_mid = agent_boxes[0][0] + agent_w / 2
    last_mid = agent_boxes[-1][0] + agent_w / 2
    svg.line([(first_mid, task_bus), (last_mid, task_bus)], arrow=False)
    svg.text(552, task_bus - 8, "typed task + selected skill; typed output returns to the code that ran it", 11.5, 400, MUTED, "start", italic=True)

    # Muse asks the application for a granted tool; it never calls an agent.
    muse = agent_boxes[1]
    tools_x = xs[2] + comp_w / 2
    svg.line([(530, agent_y - 2), (530, comp_y + 72)], dashed=True)
    svg.text(522, 446, "tool calls", 11.5, 400, MUTED, "end", italic=True)

    stores_y, store_h = 740, 74
    corpus = svg.box(130, stores_y, 240, store_h, "code", "Canonical corpus", ["five immutable books"])
    retrieval = svg.box(440, stores_y, 360, store_h, "code", "Scoped retrieval", ["BM25, dense, fusion, reranker", "scope set by the application"])
    exa = svg.box(880, stores_y, 200, store_h, "ext", "Exa web search", ["external, only when granted"])
    memory = svg.box(1120, stores_y, 250, store_h, "code", "Account memory store", ["Markdown memories,", "JSON curation events"])
    svg.line([(440, stores_y + 37), (372, stores_y + 37)])

    lib = agent_boxes[2]
    ser = agent_boxes[3]
    scu = agent_boxes[4]
    svg.line([(640, agent_y + agent_h + 2), (640, stores_y - 2)], dashed=True)
    svg.text(632, 724, "passages", 11.5, 400, MUTED, "end", italic=True)
    svg.line([(860, agent_y + agent_h + 2), (860, stores_y + 37), (802, stores_y + 37)], dashed=True)
    svg.text(852, 724, "book search", 11.5, 400, MUTED, "end", italic=True)
    svg.line([(980, agent_y + agent_h + 2), (980, stores_y - 2)], dashed=True)
    svg.text(988, 724, "web", 11.5, 400, MUTED, "start", italic=True)
    svg.line([(1070, agent_y + agent_h + 2), (1070, 690), (1160, 690), (1160, stores_y - 2)], dashed=True)
    svg.text(1168, 724, "memory search", 11.5, 400, MUTED, "start", italic=True)
    svg.line([(scu[0] + 190, agent_y + agent_h + 2), (scu[0] + 190, stores_y - 2)], dashed=True)
    svg.text(scu[0] + 182, 700, "snapshot", 11.5, 400, MUTED, "end", italic=True)

    mps_x = xs[5] + comp_w
    svg.line([(mps_x + 2, comp_y + 35), (1380, comp_y + 35), (1380, stores_y + 37), (1372, stores_y + 37)])
    svg.text(1372, 688, "writes", 11.5, 400, MUTED, "end", italic=True)

    svg.legend(30, 872, [("agent", "model-backed agent"), ("code", "deterministic code or store"), ("ext", "optional external service")])
    svg.line([(860, 872), (900, 872)])
    svg.text(908, 876.5, "calls, writes or typed tasks", 12, 400, "#333333", "start")
    svg.line([(1100, 872), (1140, 872)], dashed=True)
    svg.text(1148, 876.5, "access the application runs", 12, 400, "#333333", "start")
    return svg


# Figure 2.2: one chat turn as a sequence ------------------------------------------


def figure_chat_turn_sequence() -> Svg:
    svg = Svg(1400, 1010)
    lanes = [
        ("Reader", "code"),
        ("Application", "code"),
        ("Provenance", "agent"),
        ("Muse", "agent"),
        ("Librarian /\nSerendipity", "agent"),
        ("Memory and\nPolicy Service", "code"),
    ]
    xs = []
    for index, (name, kind) in enumerate(lanes):
        cx = 110 + index * 236
        xs.append(cx)
        svg.box(cx - 95, 20, 190, 58, kind, name.split("\n"), title_size=14)
        svg.add(
            f'<line x1="{cx}" y1="80" x2="{cx}" y2="945" stroke="#9a9a9a" '
            f'stroke-width="1.2" stroke-dasharray="5 5"/>'
        )
    reader, app, prov, muse, tools, mps = xs

    def msg(y, a, b, label, ret=False):
        svg.line([(a + (6 if b > a else -6), y), (b - (6 if b > a else -6), y)], dashed=ret)
        mid = (a + b) / 2
        rows = label.split("\n")
        for i, row in enumerate(rows):
            svg.text(mid, y - 9 - (len(rows) - 1 - i) * 17, row, 13, 400, INK)

    def activation(y, title, sub):
        svg.rect(app - 9, y - 16, 18, 40, "#ffffff", INK, 1.4, None, rx=2)
        svg.text(app + 20, y, title, 13.5, 700, INK, "start")
        svg.text(app + 20, y + 18, sub, 12, 400, MUTED, "start", italic=True)

    msg(125, reader, app, "1  Line (reader message)")
    activation(178, "2  Pre-model checks (Figure 3.9, checks 1–6)", "may end the turn with a fixed reply")
    msg(248, app, prov, "3  Emotional preflight, no tools")
    msg(298, prov, app, "continue | boundary |\nself-harm boundary", ret=True)
    msg(348, app, muse, "4  Triage, then tool grants")
    msg(398, muse, app, "5a  Muse requests a granted tool")
    msg(448, app, tools, "5b  Application supplies the reader's words and permitted scope")
    msg(498, tools, app, "5c  Typed evidence or typed decline", ret=True)
    msg(548, app, muse, "5d  Application returns the tool result", ret=True)
    msg(598, muse, app, "6  Typed candidate with evidence declarations", ret=True)
    msg(648, app, prov, "7  Candidate review, fresh context")
    msg(698, prov, app, "pass | revise (once,\nback to 5a) | reject", ret=True)
    activation(752, "8  Deterministic release checks", "quotations, citations and reading scope checked against evidence")
    msg(828, app, mps, "9  Commit nomination, if review and policy allow")
    msg(888, app, reader, "10  Released reply,\nclarification, or fixed reply", ret=True)

    svg.legend(30, 980, [("agent", "model-backed agent"), ("code", "deterministic code")])
    svg.line([(420, 980), (460, 980)])
    svg.text(468, 984.5, "call", 12, 400, "#333333", "start")
    svg.line([(530, 980), (570, 980)], dashed=True)
    svg.text(578, 984.5, "return", 12, 400, "#333333", "start")
    return svg


# Figure 2.3: physical architecture ----------------------------------------------


def figure_physical_architecture() -> Svg:
    svg = Svg(1400, 620)
    svg.rect(330, 20, 760, 540, "#f6f6f6", "#c9c9c9", 1.2, None, rx=6)
    svg.text(348, 44, "RAILWAY SERVICE · ONE REPLICA · ONE CONTAINER", 12, 700, "#666666", "start")
    svg.rect(352, 62, 470, 480, "#fbfbfb", "#9a9a9a", 1.2, "6 4", rx=6)
    svg.text(370, 530, "ONE UVICORN PROCESS · PYTHON 3.12 · ONE WORKER", 11.5, 700, "#666666", "start")

    fastapi = svg.box(380, 82, 414, 86, "code", "FastAPI application", ["built React assets · /api · SSE chat stream", "chat sessions and rate limiter in process memory"])
    agents = svg.box(380, 208, 414, 74, "agent", "Five Pydantic AI agents", ["one reusable Agent per role, skill chosen per run"])
    retrieval = svg.box(380, 322, 414, 74, "code", "Retrieval code and local models", ["BM25 · bge-small-en-v1.5 · MiniLM reranker (CPU)"])
    corpus = svg.box(380, 436, 414, 66, "code", "Canonical corpus", ["five immutable books"])
    svg.line([(587, 168), (587, 206)])
    svg.text(597, 192, "in-process", 11.5, 400, MUTED, "start", italic=True)
    svg.line([(587, 282), (587, 320)])
    svg.text(597, 306, "granted tools", 11.5, 400, MUTED, "start", italic=True)
    svg.line([(587, 396), (587, 434)])

    secrets = svg.box(850, 90, 220, 96, "code", "Runtime secrets", ["env vars: provider and", "Exa keys; Logfire token", "only if set"])
    volume = svg.box(850, 310, 220, 170, "code", "Persistent volume", ["survives redeploys", "", "SQLite: accounts, transcripts,", "reading progress", "Markdown memories and", "JSON curation events"])
    svg.line([(823, 400), (848, 400)])

    browser = svg.box(40, 90, 230, 76, "code", "Browser", ["React 19 client"])
    svg.line([(270, 125), (378, 125)])
    svg.text(324, 116, "HTTPS", 11.5, 400, MUTED, italic=True)

    ghcr = svg.box(40, 380, 230, 96, "code", ["GitHub Container", "Registry"], ["released, scanned image"], title_size=13.5)
    svg.line([(270, 428), (350, 428)])
    svg.text(310, 418, "deploys the", 11.5, 400, MUTED, italic=True)
    svg.text(310, 452, "same image", 11.5, 400, MUTED, italic=True)

    logfire = svg.box(1150, 60, 220, 72, "ext", "Pydantic Logfire", ["metadata-only telemetry"])
    provider = svg.box(1150, 210, 220, 72, "code", "Model provider", ["OpenAI gpt-6-luna"])
    exa = svg.box(1150, 360, 220, 72, "ext", "Exa web search", ["optional, granted per turn"])
    svg.line([(794, 100), (830, 100), (830, 70), (1120, 70), (1120, 96), (1148, 96)], dashed=True)
    svg.text(980, 62, "OTLP, only when a token is set", 11.5, 400, MUTED, italic=True)
    svg.line([(794, 245), (1148, 245)])
    svg.text(1110, 237, "HTTPS", 11.5, 400, MUTED, "end", italic=True)
    svg.line([(794, 262), (830, 262), (830, 286), (1110, 286), (1110, 396), (1148, 396)], dashed=True)
    svg.text(1100, 280, "HTTPS, when enabled", 11.5, 400, MUTED, "end", italic=True)

    svg.legend(40, 592, [("agent", "model-backed agents"), ("code", "code, stores and required services"), ("ext", "optional external service")])
    return svg


# Figure 8.1: release flow ---------------------------------------------------------


def figure_release_flow() -> Svg:
    svg = Svg(1400, 650)
    ok = "#2f6b3a"
    row1, h1 = 30, 70
    ci = [
        ("PR to main", ["full CI + review"]),
        ("Promotion PR", ["source check + review"]),
        ("Merge to release-candidate", ["CI on the exact commit"]),
        ("Build release image", ["scan, startup and", "persistence checks"]),
    ]
    xs = [30, 330, 630, 930]
    for x, (title, lines) in zip(xs, ci):
        svg.box(x, row1, 250, h1, "code", title, lines)
    for a, b in zip(xs, xs[1:]):
        svg.line([(a + 252, row1 + h1 / 2), (b - 2, row1 + h1 / 2)])

    # Image checks gate both routes; a failure stops publication.
    svg.box(930, 150, 250, 70, "decision", "Image checks and", ["evidence pass?"], title_size=13.5, line_size=13.5)
    svg.line([(1055, row1 + h1 + 2), (1055, 148)])
    svg.box(700, 150, 150, 70, "stop", "STOP", ["no publication"])
    svg.line([(928, 185), (852, 185)], colour="stop")
    svg.text(890, 177, "no", 12, 650, STOP)

    # Decision row: read right to left, following the arrows.
    svg.box(930, 270, 250, 70, "decision", "Live evaluation on?")
    svg.line([(1055, 222), (1055, 268)])
    svg.text(1063, 250, "yes", 12, 650, ok, "start")
    svg.box(630, 270, 250, 70, "code", "Live replays + HTTP smoke", ["selected Scenarios on the image"])
    svg.line([(928, 305), (882, 305)])
    svg.text(905, 297, "on", 12, 650, ok)
    svg.box(330, 270, 250, 70, "decision", "Completed with no", ["security or evidence blocker?"], title_size=13.5, line_size=12)
    svg.line([(628, 305), (582, 305)])
    svg.line([(455, 268), (455, 185), (698, 185)], colour="stop")
    svg.text(465, 177, "blocked or did not complete", 12, 650, STOP, "start")
    svg.box(30, 270, 220, 70, "decision", "Score > 80% and", ["auto-publish on?"], title_size=13.5, line_size=13.5)
    svg.line([(328, 290), (252, 290)])
    svg.text(290, 282, "clear", 12, 650, ok)

    svg.box(30, 410, 220, 60, "code", "Automatic approval")
    svg.line([(140, 342), (140, 408)])
    svg.text(148, 380, "yes", 12, 650, ok, "start")
    svg.box(330, 410, 250, 60, "code", "Human approval")
    svg.line([(252, 322), (290, 322), (290, 440), (328, 440)])
    svg.text(298, 392, "no", 12, 650, ok, "start")
    # Live evaluation switched off: human approval, with no score.
    svg.line([(1055, 342), (1055, 380), (455, 380), (455, 408)])
    svg.text(1045, 372, "off: human approval required, no score", 12, 650, "#555555", "end")
    svg.box(660, 410, 140, 60, "stop", "STOP")
    svg.line([(582, 440), (658, 440)], colour="stop")
    svg.text(620, 432, "rejected", 11.5, 650, STOP)

    # Publication and operation.
    row4 = 550
    pub = [
        ("GHCR", ["publish the same checked image"]),
        ("Railway", ["exact image + readiness checks"]),
        ("Logfire", ["metadata-only monitoring"]),
        ("Human investigation", ["new tests and fixes"]),
    ]
    pxs = [30, 330, 630, 930]
    for x, (title, lines) in zip(pxs, pub):
        svg.box(x, row4, 250, 66, "code", title, lines)
    for a, b in zip(pxs, pxs[1:]):
        svg.line([(a + 252, row4 + 33), (b - 2, row4 + 33)])
    svg.line([(100, 472), (100, row4 - 2)])
    svg.line([(455, 472), (455, 510), (210, 510), (210, row4 - 2)])
    svg.text(465, 502, "approved", 12, 650, ok, "start")
    svg.box(1240, row4, 140, 66, "note", "back to", ["a new PR to main"], title_size=12.5)
    svg.line([(1182, row4 + 33), (1238, row4 + 33)], dashed=True)
    return svg


# Figure 3.3: Serendipity's live skills ------------------------------------------


def figure_serendipity_skills() -> Svg:
    svg = Svg(1060, 640)
    svg.legend(24, 26, [("code", "Application code"), ("agent", "Agent"), ("fixed", "Fixed reply, turn ends")])
    svg.box(30, 64, 230, 74, "muted", "serendipity_explore", ["Muse passes an intent;", "a pinned intent is checked"])
    svg.box(320, 64, 330, 74, "code", "Build request scope", ["active memories, confirmed reading,", "web policy; recall: memory only"])
    svg.box(780, 64, 240, 74, "fixed", "Decline", ["agent not called"])
    svg.line([(262, 101), (318, 101)])
    svg.line([(652, 101), (778, 101)])
    svg.text(715, 92, "no permitted source", 11.5, 400, MUTED, italic=True)
    svg.rect(24, 200, 1012, 276, "#f6f6f6", "#c9c9c9", 1.2, None, rx=6)
    svg.text(40, 462, "LIVE SKILLS: the intent selects one; each run is capped at 14 tool calls and 16 model requests", 12, 700, "#555555", "start")
    skills = [
        ("connection-discovery", ["Intent: find_connection or", "get_recommendation", "Searches books, memories, web", "Ranks candidates; a top-two", "tie produces a decline", "Returns ConnectionProposal", "or ConnectionDecline"]),
        ("source-gathering", ["Intent: gather_sources", "Collects every source the", "user named, side by side", "Searches books, memories, web", "Does not rank or pick a winner", "Returns SourceBundle", "or ConnectionDecline"]),
        ("memory-recall", ["Intent: recall_memory", "Searches memories only", "Finds the user's own", "earlier words on the topic", "Returns MemoryRecall", "or ConnectionDecline"]),
    ]
    xs = [44, 376, 708]
    svg.line([(485, 138), (485, 176)], arrow=False)
    svg.line([(xs[0] + 150, 176), (xs[2] + 150, 176)], arrow=False)
    for x, (name, lines) in zip(xs, skills):
        svg.line([(x + 150, 176), (x + 150, 218)])
        svg.box(x, 220, 300, 222, "agent", name, lines, title_size=14.5, line_size=12.5)
        svg.line([(x + 150, 442), (x + 150, 448)], arrow=False)
        svg.line([(x + 150, 476), (x + 150, 500)], arrow=False)
    svg.line([(xs[0] + 150, 500), (xs[2] + 150, 500)], arrow=False)
    svg.line([(345, 500), (345, 538)])
    svg.box(200, 540, 290, 74, "code", "Application recheck", ["evidence within the grant; web pages", "opened in this run; ids in run ledger"])
    svg.box(570, 540, 290, 74, "code", "Back to Muse", ["selected evidence only;", "one result cached per turn"])
    svg.line([(492, 577), (568, 577)])
    return svg


# Figure 3.4: why source-gathering exists ------------------------------------------

NAMED_SOURCES = ["Alice: the Caterpillar", "Pinocchio: the promise", "Keller: the lake", "Hume passage", "Reader's own note"]


def figure_named_sources() -> Svg:
    svg = Svg(1400, 640)
    good, bad = "#2f7a46", "#b23a2a"

    def chip(x, y, label, state):
        w, h = 172, 30
        if state == "kept":
            svg.rect(x, y, w, h, "#ffffff", INK, 1.3, None, rx=15)
            svg.text(x + w / 2, y + 19.5, label, 12, 500, INK)
        elif state == "bundle":
            svg.rect(x, y, w, h, "#e8f3ea", good, 1.5, None, rx=15)
            svg.text(x + w / 2, y + 19.5, label, 12, 600, "#1f5a33")
        else:
            svg.rect(x, y, w, h, "#f4f4f4", "#c9c9c9", 1.2, "4 3", rx=15)
            svg.text(x + w / 2, y + 19.5, label, 12, 400, "#a3a3a3")
            width = len(label) * 6.3
            svg.add(f'<line x1="{x + w / 2 - width / 2:.1f}" y1="{y + 15.5:.1f}" x2="{x + w / 2 + width / 2:.1f}" y2="{y + 15.5:.1f}" stroke="{bad}" stroke-width="1.6"/>')

    def chips(x0, y0, states):
        positions = [(0, 0), (184, 0), (0, 38), (184, 38), (92, 76)]
        for (dx, dy), label, state in zip(positions, NAMED_SOURCES, states):
            chip(x0 + dx, y0 + dy, label, state)

    columns = [
        ("1", "Rank and pick a winner", "connection-discovery"),
        ("2", "Add a prompt rule", "connection-discovery + instruction"),
        ("3", "Gather into a bundle", "source-gathering"),
    ]
    col_w, gap, x0 = 420, 40, 30
    for index, (number, title, skill) in enumerate(columns):
        x = x0 + index * (col_w + gap)
        mid = x + col_w / 2
        svg.badge(x + 14, 40, number, "#444444")
        svg.text(x + 34, 45, title, 16, 700, INK, "start")
        if index:
            svg.line([(x - gap + 6, 40), (x - 8, 40)], colour="muted")

        # The same request in every column.
        svg.rect(x, 66, col_w, 150, "#f7f7f7", "#d6d6d6", 1, None, rx=8)
        svg.text(x + 16, 88, "Reader names five sources to compare", 12.5, 650, "#444444", "start")
        chips(x + 30, 100, ["kept"] * 5)
        svg.line([(mid, 218), (mid, 246)])

        if index == 0:
            svg.box(x, 248, col_w, 64, "agent", skill, ["ranks candidates, returns one winner"])
        elif index == 1:
            svg.box(x, 248, col_w, 64, "agent", skill, ["“the winner must cover every named source”"])
        else:
            svg.box(x, 248, col_w, 64, "agent", skill, ["collects each named source; no ranking, no winner"])
        svg.line([(mid, 314), (mid, 342)])

        if index < 2:
            svg.rect(x, 344, col_w, 150, "#ffffff", INK, 1.4, None, rx=8)
            svg.text(x + 16, 366, "One winner", 12.5, 650, INK, "start")
            svg.text(x + col_w - 16, 366, "or a decline", 12, 400, MUTED, "end", italic=True)
            chips(x + 30, 378, ["kept", "dropped", "dropped", "kept", "dropped"])
        else:
            svg.rect(x, 344, col_w, 150, "#ffffff", good, 1.8, None, rx=8)
            svg.text(x + 16, 366, "One bundle", 12.5, 650, "#1f5a33", "start")
            svg.text(x + col_w - 16, 366, "not found: none", 12, 400, MUTED, "end", italic=True)
            chips(x + 30, 378, ["bundle"] * 5)

        outcomes = [
            (bad, "#fbe4e2", ["Named sources dropped, or declined", "Scenes 06 and 07: no passes before run 11"]),
            (bad, "#fbe4e2", ["No effect", "Serendipity ignored the instruction"]),
            (good, "#e8f3ea", ["Every named source reaches Muse", "Scenes 06 and 07: 7 passes in 10 (runs 11 to 15)"]),
        ]
        colour, fill, rows = outcomes[index]
        svg.rect(x, 512, col_w, 70, fill, colour, 1.4, None, rx=8)
        svg.text(mid, 540, rows[0], 14, 700, colour)
        svg.text(mid, 562, rows[1], 12.5, 400, "#333333")

    svg.text(
        30,
        616,
        "Sources from the Scene 07 request. Which sources a winner kept varied by run; the passes in column 3 also include the retrieval fixes made in the same runs.",
        12,
        400,
        MUTED,
        "start",
        italic=True,
    )
    return svg


FIGURES = {
    "fig-3-4-named-sources": figure_named_sources,
    "fig-3-3-serendipity-skills": figure_serendipity_skills,
    "fig-2-1-logical-architecture": figure_logical_architecture,
    "fig-2-2-chat-turn-sequence": figure_chat_turn_sequence,
    "fig-2-3-physical-architecture": figure_physical_architecture,
    "fig-3-8-turn-strip": figure_turn_strip,
    "fig-6-1-security-checkpoints": figure_security_checkpoints,
    "fig-7-1-test-coverage": figure_test_coverage,
    "fig-8-1-release-flow": figure_release_flow,
    "fig-10-1-evidence-loss": figure_evidence_loss,
    "fig-10-3-provenance-verdicts": figure_provenance_verdicts,
    "fig-10-4-provenance-examples": figure_provenance_examples,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in FIGURES.items():
        (OUT / f"{name}.svg").write_text(build().render(), encoding="utf-8")
        print(f"wrote {name}.svg")


if __name__ == "__main__":
    main()
