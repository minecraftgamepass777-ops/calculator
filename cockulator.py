import ast
import operator
import re

import customtkinter as ctk

# ───────────────────────── Palette ─────────────────────────
BG = "#0b0d12"
CARD = "#131722"
PANEL = "#10131b"
NUM, NUM_H = "#1a1f2b", "#262d3d"
FN, FN_H = "#262c3b", "#343c52"
TEXT = "#eef1f8"
MUTED = "#7c869c"
ERR = "#ff6b7a"

ACCENTS = [
    ("Cyan", "#22d3ee"),
    ("Violet", "#a78bfa"),
    ("Pink", "#f472b6"),
    ("Lime", "#a3e635"),
    ("Amber", "#fbbf24"),
]

OPS = "+−×÷"

LAYOUT = [
    [("C", "fn"), ("⌫", "fn"), ("%", "fn"), ("÷", "op")],
    [("7", "num"), ("8", "num"), ("9", "num"), ("×", "op")],
    [("4", "num"), ("5", "num"), ("6", "num"), ("−", "op")],
    [("1", "num"), ("2", "num"), ("3", "num"), ("+", "op")],
    [("±", "fn"), ("0", "num"), (".", "num"), ("=", "eq")],
]


# ───────────────────── Helpers / math engine ─────────────────────
def mix(c1: str, c2: str, t: float) -> str:
    """Blend two hex colors. t=1 -> c1, t=0 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(a, b))


_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_eval(expr: str):
    """Evaluate + - * / and parentheses without using eval()."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
            return _UN[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")

    return ev(ast.parse(expr, mode="eval"))


def to_py(expr: str) -> str:
    return (
        expr.replace("−", "-").replace("×", "*").replace("÷", "/").replace("%", "/100")
    )


def fmt(v) -> str:
    """Format a number for display (uses the pretty minus sign)."""
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("not finite")
        if v.is_integer() and abs(v) < 1e15:
            s = str(int(v))
        else:
            s = f"{v:.12g}"
    else:
        s = str(v)
        if len(s.lstrip("-")) > 15:
            s = f"{float(v):.10g}"
    return s.replace("-", "−")


def prettify(expr: str) -> str:
    """Add breathing room around binary operators for display."""
    return re.sub(r"(?<=[\d)%])([+−×÷])", r" \1 ", expr)


NUM_TAIL = re.compile(r"\d*\.?\d*$")
NEG_GROUP_TAIL = re.compile(r"\(−(\d+\.?\d*)\)$")
NUMBER_ONLY = re.compile(r"−?\d*\.?\d+|−?\d+\.|\(−\d+\.?\d*\)")


class Engine:
    """Pure calculator state machine (no UI code)."""

    def __init__(self):
        self.expr = ""
        self.sub = ""  # "12 × 3 =" after evaluating
        self.done = False  # True right after "="
        self.error = None
        self.history = []  # [(expression, result)]

    # -- public --
    def press(self, key: str):
        if self.error:
            self.expr, self.sub, self.error, self.done = "", "", None, False
        if key == "C":
            self.expr, self.sub, self.done = "", "", False
        elif key == "⌫":
            self._back()
        elif key == "=":
            self._equals()
        elif key == "±":
            self._negate()
        elif key == "%":
            self._percent()
        elif key in OPS:
            self._operator(key)
        elif key == ".":
            self._dot()
        elif key.isdigit():
            self._digit(key)

    def preview(self) -> str:
        if self.done or self.error or not self.expr:
            return ""
        e = self._strip_ops(self.expr)
        if not e or NUMBER_ONLY.fullmatch(e):
            return ""
        try:
            return "= " + fmt(safe_eval(to_py(e)))
        except Exception:
            return ""

    def load(self, value: str):
        self.expr, self.sub, self.error, self.done = value, "", None, True

    # -- internals --
    @staticmethod
    def _strip_ops(e: str) -> str:
        while e and e[-1] in OPS:
            e = e[:-1]
        return e

    def _fresh(self):
        if self.done:
            self.expr, self.sub, self.done = "", "", False

    def _release(self):
        if self.done:
            self.sub, self.done = "", False

    def _digit(self, d):
        self._fresh()
        if self.expr and self.expr[-1] in ")%":
            self.expr += "×"
        tok = NUM_TAIL.search(self.expr).group()
        if len(tok) >= 15:
            return
        if tok == "0":
            self.expr = self.expr[:-1]
        self.expr += d

    def _dot(self):
        self._fresh()
        if self.expr and self.expr[-1] in ")%":
            self.expr += "×"
        tok = NUM_TAIL.search(self.expr).group()
        if "." in tok:
            return
        self.expr += "0." if tok == "" else "."

    def _operator(self, op):
        self._release()
        if not self.expr:
            self.expr = "−" if op == "−" else "0" + op
            return
        if self.expr == "−":
            return
        if self.expr[-1] in OPS:
            self.expr = self.expr[:-1] + op
        else:
            self.expr += op

    def _percent(self):
        if self.expr and self.expr[-1] in "0123456789)%":
            self._release()
            self.expr += "%"

    def _negate(self):
        self._release()
        m = NEG_GROUP_TAIL.search(self.expr)
        if m:
            self.expr = self.expr[:m.start()] + m.group(1)
            return
        m = re.search(r"\d+\.?\d*$", self.expr)
        if m:
            self.expr = self.expr[:m.start()] + "(−" + m.group() + ")"

    def _back(self):
        self._release()
        m = re.search(r"\(−\d*\.?\d*\)$", self.expr)
        self.expr = self.expr[:m.start()] if m else self.expr[:-1]

    def _equals(self):
        e = self._strip_ops(self.expr)
        if not e or NUMBER_ONLY.fullmatch(e):
            return
        try:
            result = fmt(safe_eval(to_py(e)))
        except ZeroDivisionError:
            self.error, self.sub = "Can't divide by zero", e + " ="
            return
        except Exception:
            self.error, self.sub = "Error", ""
            return
        self.history.append((e, result))
        self.sub, self.expr, self.done = e + " =", result, True


# ───────────────────────── UI ─────────────────────────
class Calculator(ctk.CTk):
    W, H, PANEL_W = 368, 640, 250

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Neon Calc")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        x = (self.winfo_screenwidth() - self.W) // 2
        y = (self.winfo_screenheight() - self.H) // 2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.engine = Engine()
        self.accent = ACCENTS[0][1]
        self.history_open = False
        self.buttons, self.kinds = {}, {}
        self.swatches = []
        self.hist_widgets = []

        self.grid_rowconfigure(0, weight=1)
        self._build_calc()
        self._build_history()

        self.bind("<Key>", self._on_key)
        self.apply_theme()
        self.refresh()

    # ---- building ----
    def _build_calc(self):
        self.calc = ctk.CTkFrame(self, fg_color="transparent", width=self.W, height=self.H)
        self.calc.grid(row=0, column=0, sticky="nsw")
        self.calc.pack_propagate(False)

        # top bar: accent dots + history toggle
        bar = ctk.CTkFrame(self.calc, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(16, 4))
        for _, color in ACCENTS:
            dot = ctk.CTkButton(
                bar, text="", width=22, height=22, corner_radius=11,
                fg_color=color, hover_color=color, border_width=2, border_color=BG,
                command=lambda c=color: self.set_accent(c),
            )
            dot.pack(side="left", padx=3)
            self.swatches.append((dot, color))
        self.hist_btn = ctk.CTkButton(
            bar, text="History", width=78, height=28, corner_radius=14,
            font=ctk.CTkFont(size=13, weight="bold"), command=self.toggle_history,
        )
        self.hist_btn.pack(side="right")

        # display card
        self.card = ctk.CTkFrame(self.calc, fg_color=CARD, corner_radius=26, border_width=1)
        self.card.pack(fill="x", padx=12, pady=(8, 10))
        self.card.grid_columnconfigure(0, weight=1)
        self.sub_font = ctk.CTkFont(size=17)
        self.main_font = ctk.CTkFont(size=50, weight="bold")
        self.sub = ctk.CTkLabel(self.card, text=" ", font=self.sub_font, anchor="e", height=26)
        self.sub.grid(row=0, column=0, sticky="ew", padx=22, pady=(24, 0))
        self.main = ctk.CTkLabel(
            self.card, text="0", font=self.main_font, anchor="e", height=76, text_color=TEXT
        )
        self.main.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 20))

        # keypad
        pad = ctk.CTkFrame(self.calc, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for c in range(4):
            pad.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(len(LAYOUT)):
            pad.grid_rowconfigure(r, weight=1, uniform="row")
        for r, row in enumerate(LAYOUT):
            for c, (key, kind) in enumerate(row):
                b = ctk.CTkButton(
                    pad, text=key, height=64, corner_radius=22,
                    font=ctk.CTkFont(size=24, weight="bold"),
                    command=lambda k=key: self.press(k),
                )
                b.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                self.buttons[key], self.kinds[key] = b, kind

    def _build_history(self):
        self.hist_panel = ctk.CTkFrame(
            self, fg_color=PANEL, corner_radius=0, width=self.PANEL_W, height=self.H
        )
        self.hist_panel.pack_propagate(False)

        head = ctk.CTkFrame(self.hist_panel, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(18, 6))
        ctk.CTkLabel(
            head, text="History", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT
        ).pack(side="left")
        self.hist_clear = ctk.CTkButton(
            head, text="Clear", width=56, height=26, corner_radius=13,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=FN, hover_color=FN_H, text_color=MUTED, command=self.clear_history,
        )
        self.hist_clear.pack(side="right")

        self.hist_list = ctk.CTkScrollableFrame(self.hist_panel, fg_color="transparent")
        self.hist_list.pack(fill="both", expand=True, padx=6, pady=(0, 10))

    # ---- styling ----
    def style(self, kind: str) -> dict:
        a = self.accent
        if kind == "num":
            return dict(fg_color=NUM, hover_color=NUM_H, text_color=TEXT)
        if kind == "fn":
            return dict(fg_color=FN, hover_color=FN_H, text_color="#c9d1e3")
        if kind == "op":
            return dict(fg_color=mix(a, BG, 0.16), hover_color=mix(a, BG, 0.30), text_color=a)
        return dict(fg_color=a, hover_color=mix(a, "#ffffff", 0.75), text_color="#0b0d12")

    def apply_theme(self):
        a = self.accent
        for key, b in self.buttons.items():
            b.configure(**self.style(self.kinds[key]))
        self.card.configure(border_color=mix(a, CARD, 0.35))
        self.hist_btn.configure(
            fg_color=mix(a, BG, 0.18), hover_color=mix(a, BG, 0.32), text_color=a
        )
        for dot, color in self.swatches:
            dot.configure(border_color=TEXT if color == a else BG)

    def set_accent(self, color: str):
        self.accent = color
        self.apply_theme()
        self.refresh()

    def flash(self, key: str):
        b = self.buttons.get(key)
        if not b:
            return
        kind = self.kinds[key]
        base = self.style(kind)["fg_color"]
        b.configure(fg_color="#ffffff" if kind == "eq" else mix(self.accent, base, 0.55))
        self.after(110, lambda: b.configure(fg_color=self.style(kind)["fg_color"]))

    # ---- behavior ----
    def press(self, key: str):
        self.flash(key)
        before = len(self.engine.history)
        self.engine.press(key)
        if len(self.engine.history) != before:
            self.render_history()
        self.refresh()

    def _on_key(self, e):
        k, c = e.keysym, e.char
        if k in ("Return", "KP_Enter"):
            self.press("=")
        elif k == "BackSpace":
            self.press("⌫")
        elif k in ("Escape", "Delete"):
            self.press("C")
        elif c and c in "0123456789.":
            self.press(c)
        elif c in ("+", "-", "*", "/", "%", "=", "x"):
            self.press({"-": "−", "*": "×", "x": "×", "/": "÷"}.get(c, c))

    @staticmethod
    def _size_for(n: int) -> int:
        for limit, size in ((8, 50), (10, 42), (13, 34), (17, 27), (22, 21)):
            if n <= limit:
                return size
        return 17

    def refresh(self):
        e = self.engine
        if e.error:
            main, color = e.error, ERR
        else:
            main, color = prettify(e.expr) or "0", TEXT
        self.main.configure(text=main, text_color=color)
        self.main_font.configure(size=self._size_for(len(main)))

        if e.sub:
            self.sub.configure(text=prettify(e.sub), text_color=MUTED)
        else:
            self.sub.configure(text=e.preview() or " ", text_color=self.accent)

    # ---- history ----
    def toggle_history(self):
        self.history_open = not self.history_open
        if self.history_open:
            self.hist_panel.grid(row=0, column=1, sticky="ns")
            self.geometry(f"{self.W + self.PANEL_W}x{self.H}")
            self.render_history()
        else:
            self.hist_panel.grid_remove()
            self.geometry(f"{self.W}x{self.H}")

    def render_history(self):
        for w in self.hist_widgets:
            w.destroy()
        self.hist_widgets.clear()
        if not self.engine.history:
            lbl = ctk.CTkLabel(
                self.hist_list, text="No calculations yet", text_color=MUTED,
                font=ctk.CTkFont(size=13),
            )
            lbl.pack(pady=30)
            self.hist_widgets.append(lbl)
            return
        for expr, res in reversed(self.engine.history[-50:]):
            b = ctk.CTkButton(
                self.hist_list, text=f"{prettify(expr)} =\n{res}", anchor="e", height=54,
                corner_radius=14, fg_color=CARD, hover_color=FN_H, text_color=TEXT,
                font=ctk.CTkFont(size=14), command=lambda r=res: self.recall(r),
            )
            b.pack(fill="x", pady=3, padx=4)
            self.hist_widgets.append(b)

    def recall(self, value: str):
        self.engine.load(value)
        self.refresh()

    def clear_history(self):
        self.engine.history.clear()
        self.render_history()


if __name__ == "__main__":
    Calculator().mainloop()

