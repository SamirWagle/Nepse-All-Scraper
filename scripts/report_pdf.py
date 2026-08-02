"""Shared styled PDF builder for investor-persona analysis reports.

Used by all investing-greats skills (rakesh-jhunjhunwala, mohnish-pabrai,
charlie-munger, phil-fisher, bill-ackman, stanley-druckenmiller, peter-lynch,
nassim-taleb) so every {TICKER}_{Analyst}_Analysis.pdf shares one of the
3 approved visual templates from ~/Desktop/PDf designs/ (Designa/b/c.pdf)
instead of each skill hand-rolling fpdf2 calls.

Per user instruction: every PDF Claude generates picks one of the 3 templates
at RANDOM (Report.__init__ does this - no caller-side selection needed).

fpdf2 gotcha: multi_cell(width=0, ...) leaves cursor x at the right margin
instead of resetting left, so the next multi_cell call can raise
"Not enough horizontal space to render a single character". Every text call
here passes new_x=XPos.LMARGIN, new_y=YPos.NEXT to avoid it.
"""
import random

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_UNICODE_ASCII_MAP = str.maketrans({
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...",
})


def _s(txt):
    """Core Helvetica/Times fonts only support latin-1 - downgrade common
    Unicode punctuation (em/en dash, curly quotes, ellipsis) rather than
    crashing."""
    return str(txt).translate(_UNICODE_ASCII_MAP)


BLACK = (20, 20, 20)
GREY = (110, 110, 110)
GREEN = (40, 120, 70)
GREEN_BG = (232, 242, 235)
RED = (175, 55, 55)
RED_BG = (250, 235, 235)
AMBER = (150, 115, 25)
AMBER_BG = (250, 243, 224)

GOLD = (168, 130, 40)
CREAM = (250, 247, 240)
TAN_CARD = (245, 238, 222)
BLUE = (35, 100, 170)

SIGNAL_COLOR = {
    "BULLISH": (GREEN, GREEN_BG),
    "BUY-CASE": (GREEN, GREEN_BG),
    "BEARISH": (RED, RED_BG),
    "SELL-CASE": (RED, RED_BG),
    "NEUTRAL": (AMBER, AMBER_BG),
    "HOLD": (AMBER, AMBER_BG),
}

_TAG_COLOR = {
    "PASS": (GREEN, GREEN_BG),
    "FAIL": (RED, RED_BG),
}


def _tag_color(score):
    key = score.upper().split()[0].rstrip("*.,")
    return _TAG_COLOR.get(key, (GREY, (240, 240, 240)))


class Report(FPDF):
    STYLES = ("a", "b", "c")

    def __init__(self, ticker, company_name, analyst, style=None):
        super().__init__()
        self.ticker = ticker
        self.company_name = company_name
        self.analyst = analyst
        self.style = style if style in self.STYLES else random.choice(self.STYLES)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()
        self.add_page()
        getattr(self, f"_cover_{self.style}")()

    # ---- chrome ---------------------------------------------------------

    def header(self):
        if self.page_no() == 1:
            return
        rule = {"a": GOLD, "b": TAN_CARD, "c": BLACK}[self.style]
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.set_y(10)
        self.cell(0, 5, _s(f"{self.ticker} - {self.analyst}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self.set_draw_color(*rule)
        self.set_line_width(0.4)
        self.line(18, 16, 192, 16)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")

    # ---- covers (one per template) --------------------------------------

    def _cover_a(self):
        """Design A: editorial serif, gold rule, italic subtitle."""
        self.set_xy(18, 14)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*GOLD)
        self.cell(0, 5, _s(f"{self.analyst.upper()}-STYLE ANALYSIS"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        self.set_x(18)
        self.set_font("Times", "", 24)
        self.set_text_color(*BLACK)
        self.cell(0, 11, _s(self.company_name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(18)
        self.set_font("Times", "I", 12)
        self.set_text_color(*GREY)
        self.cell(0, 7, _s(f"{self.ticker} - {self.analyst}-style read"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(*GOLD)
        self.set_line_width(0.6)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(6)
        self.set_text_color(*BLACK)

    def _cover_b(self):
        """Design B: bold sans, card-grid identity."""
        self.set_xy(18, 14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*GOLD)
        self.cell(0, 5, _s(f"{self.analyst.upper()}-STYLE ANALYSIS"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(18)
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*BLACK)
        self.cell(0, 10, _s(self.company_name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(18)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GREY)
        self.cell(0, 6, _s(f"{self.ticker} scorecard"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)
        self.set_text_color(*BLACK)

    def _cover_c(self):
        """Design C: two-column-flavoured serif, black rule."""
        self.set_xy(18, 14)
        self.set_font("Times", "B", 20)
        self.set_text_color(*BLACK)
        self.cell(0, 10, _s(self.company_name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(18)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GREY)
        self.cell(0, 6, _s(f"{self.analyst.upper()}-STYLE ANALYSIS"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(*BLACK)
        self.set_line_width(0.5)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(6)
        self.set_text_color(*BLACK)

    # ---- shared content API (style-dispatched) ---------------------------

    def mc(self, txt, h=5, size=10, style="", color=BLACK):
        font = "Times" if self.style in ("a", "c") else "Helvetica"
        self.set_font(font, style, size)
        self.set_text_color(*color)
        self.multi_cell(0, h, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def note(self, txt):
        """Small italic grey methodology/source note."""
        font = "Times" if self.style in ("a", "c") else "Helvetica"
        self.set_font(font, "I", 8.5)
        self.set_text_color(*GREY)
        self.multi_cell(0, 4.5, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def section(self, title):
        self.ln(2)
        if self.style == "a":
            self.set_font("Times", "", 15)
            self.set_text_color(*BLACK)
            self.cell(0, 8, _s(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(*GOLD)
            self.set_line_width(0.3)
            self.line(18, self.get_y(), 192, self.get_y())
        elif self.style == "b":
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(*BLACK)
            self.cell(0, 8, _s(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(*GOLD)
            self.cell(0, 6, _s(title.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.2)
            self.line(18, self.get_y(), 192, self.get_y())
        self.set_text_color(*BLACK)
        self.ln(2)

    def scored_row(self, label, score, detail):
        """One checklist/criterion item - card (b) or ruled row (a/c)."""
        tag_fg, tag_bg = _tag_color(score)
        if self.style == "b":
            label_w = 150
            top = self.get_y()
            self.set_font("Helvetica", "B", 10.5)
            label_lines = self.multi_cell(label_w, 5.5, _s(label), dry_run=True, output="LINES")
            self.set_font("Helvetica", "", 9.5)
            detail_lines = self.multi_cell(174, 5, _s(detail), dry_run=True, output="LINES")
            box_h = len(label_lines) * 5.5 + len(detail_lines) * 5 + 4
            self.set_fill_color(*TAN_CARD)
            self.rect(18, top - 2, 174, box_h, "F")

            self.set_xy(18, top)
            self.set_font("Helvetica", "B", 10.5)
            self.set_text_color(*BLACK)
            self.multi_cell(label_w, 5.5, _s(label), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            label_bottom = self.get_y()
            self.set_xy(18 + label_w, top)
            self.set_fill_color(*tag_bg)
            self.set_text_color(*tag_fg)
            self.set_font("Helvetica", "B", 8)
            self.cell(174 - label_w, 5.5, _s(score), fill=True, align="C")
            self.set_xy(18, label_bottom)
            self.set_font("Helvetica", "", 9.5)
            self.set_text_color(*BLACK)
            self.multi_cell(174, 5, _s(detail), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2.5)
            return

        font = "Times" if self.style == "a" else "Helvetica"
        self.set_font(font, "B", 10.5)
        self.set_text_color(*BLACK)
        label_w = 155
        y0 = self.get_y()
        label_lines = self.multi_cell(label_w, 6, _s(label), dry_run=True, output="LINES")
        row_h = max(len(label_lines), 1) * 6
        self.multi_cell(label_w, 6, _s(label), new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_xy(18 + label_w, y0)
        self.set_text_color(*tag_fg)
        self.set_font("Helvetica", "B", 9)
        self.cell(174 - label_w, 6, _s(score), align="R")
        self.set_xy(18, y0 + row_h)
        self.set_font(font, "", 9.8)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 5, _s(detail), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2.2)

    def bullet(self, txt, num=None):
        prefix = f"{num}. " if num is not None else "-  "
        font = "Times" if self.style in ("a", "c") else "Helvetica"
        italic = "I" if self.style == "c" else ""
        self.set_font(font, italic, 9.8)
        self.set_text_color(*BLACK)
        self.set_x(22)
        self.multi_cell(174, 5, _s(f"{prefix}{txt}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def signal_banner(self, signal_label, one_liner=""):
        fg, bg = AMBER, AMBER_BG
        for word, (f, b) in SIGNAL_COLOR.items():
            if word in signal_label.upper():
                fg, bg = f, b
                break
        self.ln(1)
        top = self.get_y()
        if self.style == "b":
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*fg)
            self.cell(0, 5, _s(f"SIGNAL: {signal_label.upper()}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            font = "Times" if self.style in ("a", "c") else "Helvetica"
            self.set_fill_color(*bg)
            self.set_text_color(*fg)
            self.set_font(font, "B", 11)
            self.cell(0, 8, _s(f"  Signal: {signal_label}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*BLACK)
        if one_liner:
            self.ln(1.5)
            self.mc(one_liner, h=5, size=9.8, style="I" if self.style != "b" else "")
        self.ln(2)

    def devils_advocate(self, points):
        self.section("Devil's Advocate")
        for i, p in enumerate(points, 1):
            self.bullet(p, num=i)

    def net_read(self, txt):
        self.ln(2)
        if self.style == "b":
            top = self.get_y()
            self.set_font("Helvetica", "", 9.8)
            body_lines = self.multi_cell(0, 5, _s(txt), dry_run=True, output="LINES")
            box_h = 6 + len(body_lines) * 5 + 4
            self.set_fill_color(*CREAM)
            self.set_draw_color(*GOLD)
            self.rect(18, top - 2, 174, box_h, "DF")
            self.set_y(top)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*AMBER)
            self.cell(0, 6, "NET READ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Helvetica", "", 9.8)
            self.set_text_color(*BLACK)
            self.multi_cell(0, 5, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            return
        font = "Times" if self.style in ("a", "c") else "Helvetica"
        self.set_font(font, "B", 10.5)
        self.set_text_color(*BLACK)
        self.cell(0, 6, "Net read:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(font, "", 9.8)
        self.multi_cell(0, 5, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def save(self, path):
        self.output(path)
