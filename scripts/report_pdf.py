"""Shared styled PDF builder for investor-persona analysis reports.

Used by all investing-greats skills (rakesh-jhunjhunwala, mohnish-pabrai,
charlie-munger, phil-fisher, bill-ackman, stanley-druckenmiller, peter-lynch,
nassim-taleb) so every {TICKER}_{Analyst}_Analysis.pdf on the Desktop shares
one visual style instead of each skill hand-rolling fpdf2 calls.

fpdf2 gotcha: multi_cell(width=0, ...) leaves cursor x at the right margin
instead of resetting left, so the next multi_cell call can raise
"Not enough horizontal space to render a single character". Every text call
here passes new_x=XPos.LMARGIN, new_y=YPos.NEXT to avoid it.
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

_UNICODE_ASCII_MAP = str.maketrans({
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...",
})


def _s(txt):
    """Core Helvetica font only supports latin-1 - downgrade common Unicode
    punctuation (em/en dash, curly quotes, ellipsis) rather than crashing."""
    return str(txt).translate(_UNICODE_ASCII_MAP)

NAVY = (23, 42, 68)
ACCENT = (0, 120, 130)
GREY = (110, 110, 110)
LIGHT_BG = (240, 243, 245)
GREEN = (30, 120, 60)
RED = (170, 40, 40)
BLACK = (20, 20, 20)

SIGNAL_COLOR = {
    "BULLISH": GREEN,
    "BUY-CASE": GREEN,
    "BEARISH": RED,
    "SELL-CASE": RED,
    "NEUTRAL": (150, 120, 20),
    "HOLD": (150, 120, 20),
}


class Report(FPDF):
    def __init__(self, ticker, company_name, analyst):
        super().__init__()
        self.ticker = ticker
        self.company_name = company_name
        self.analyst = analyst
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()
        self.add_page()
        self._cover_band()

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.set_y(10)
        self.cell(0, 5, _s(f"{self.ticker} - {self.analyst}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.4)
        self.line(18, 16, 192, 16)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")

    def _cover_band(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 38, "F")
        self.set_xy(18, 10)
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(255, 255, 255)
        self.cell(0, 9, _s(self.company_name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(18)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(200, 215, 220)
        self.cell(0, 7, _s(f"{self.analyst}-Style Analysis  |  {self.ticker}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(44)
        self.set_text_color(*BLACK)

    def mc(self, txt, h=5, size=10, style="", color=BLACK):
        self.set_font("Helvetica", style, size)
        self.set_text_color(*color)
        self.multi_cell(0, h, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def note(self, txt):
        """Small italic grey methodology/source note."""
        self.mc(txt, h=4.5, size=8.5, style="I", color=GREY)
        self.ln(3)

    def section(self, title):
        self.ln(2)
        self.set_fill_color(*LIGHT_BG)
        self.set_draw_color(*ACCENT)
        self.set_text_color(*NAVY)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, _s(f"  {title}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, border="L")
        self.set_text_color(*BLACK)
        self.ln(1.5)

    def scored_row(self, label, score, detail):
        """One checklist/criterion row with a bold label+score line and detail below."""
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 6, _s(f"{label}  -  {score}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 9.8)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 5, _s(detail), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2.2)

    def bullet(self, txt, num=None):
        prefix = f"{num}. " if num is not None else "-  "
        self.set_font("Helvetica", "", 9.8)
        self.set_text_color(*BLACK)
        self.set_x(22)
        self.multi_cell(174, 5, _s(f"{prefix}{txt}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def signal_banner(self, signal_label, one_liner=""):
        color = NAVY
        for word, c in SIGNAL_COLOR.items():
            if word in signal_label.upper():
                color = c
                break
        self.ln(1)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 9, _s(f"  Signal: {signal_label}  "), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*BLACK)
        if one_liner:
            self.ln(1.5)
            self.mc(one_liner, h=5, size=9.8)
        self.ln(2)

    def devils_advocate(self, points):
        self.section("Devil's Advocate")
        for i, p in enumerate(points, 1):
            self.bullet(p, num=i)

    def net_read(self, txt):
        self.ln(2)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*NAVY)
        self.cell(0, 6, "Net read:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 9.8)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 5, _s(txt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def save(self, path):
        self.output(path)
