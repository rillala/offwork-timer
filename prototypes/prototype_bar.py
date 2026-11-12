"""PROTOTYPE（用完即丟，不要合進正式程式）——浮動條該長什麼樣子？用什麼字型？

5 個結構不同的浮動條版本 × 5 組中英字型，顯示在跟正式版一樣的右下角位置。
底部白色切換列：←/→ 版本、↑/↓ 模擬時間情境、F 字型組合、Esc 結束。
執行：python prototype_bar.py [--variant C] [--font 2]
不讀寫 config.json / state.json；app.py 沒有 import 本檔，PyInstaller 不會打包它。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 專案根目錄
import argparse
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, time as dtime, timedelta

import app  # noqa: F401  借用 DPI 設定
from app import force_topmost, monitor_rect, round_corners
from theme import BG, BLUE, GREEN, RED, SUBTEXT, SURFACE, TEXT, YELLOW
from worktime import calc_off_time, fmt_delta

# (名稱, 中文字型, 數字/英文字型)
FONTSETS = [
    ("現行：正黑體 UI（中英同字）", "Microsoft JhengHei UI", "Microsoft JhengHei UI"),
    ("正黑體 UI ＋ Segoe UI Variable", "Microsoft JhengHei UI", "Segoe UI Variable Display"),
    ("正黑體 UI ＋ Bahnschrift", "Microsoft JhengHei UI", "Bahnschrift"),
    ("正黑體 UI ＋ Cascadia Mono", "Microsoft JhengHei UI", "Cascadia Mono"),
    ("正黑體 UI ＋ Consolas", "Microsoft JhengHei UI", "Consolas"),
]   # 只用 Windows 內建字型；Segoe UI Variable / Cascadia Mono 僅 Win11 內建
FS = {"i": 0}


def zh(size, bold=False):
    return (FONTSETS[FS["i"]][1], size, "bold" if bold else "normal")


def num(size, bold=False):
    return (FONTSETS[FS["i"]][2], size, "bold" if bold else "normal")


def mixed_text(cv, x, y, parts, anchor="w"):
    """在 Canvas 上畫中英混排：parts=[(文字, font, 顏色), ...]，anchor 為 w / center / e。"""
    widths = [tkfont.Font(font=f).measure(t) for t, f, _c in parts]
    total = sum(widths)
    x0 = x - total / 2 if anchor == "center" else x - total if anchor == "e" else x
    for (t, f, c), w in zip(parts, widths):
        cv.create_text(x0, y, text=t, font=f, fill=c, anchor="w")
        x0 += w


TODAY = datetime.now().date()
START = datetime.combine(TODAY, dtime(8, 30))
LUNCH = (dtime(12, 0), dtime(13, 30))
END = calc_off_time(START, 8, *LUNCH)

SCENARIOS = [
    ("剩 3 小時多（藍）", END - timedelta(hours=3, minutes=12)),
    ("午休中", datetime.combine(TODAY, dtime(12, 40))),
    ("剩 45 分（黃）", END - timedelta(minutes=45)),
    ("剩 12 分（紅）", END - timedelta(minutes=12)),
    ("已超時 15 分（綠）", END + timedelta(minutes=15)),
    ("現在（實際時間）", None),
]


def mix(c1, c2, t):
    """c1 與 c2 混色，t=1 → 全 c1。"""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(a, b))


def make_view(now):
    left = END - now
    mins = left.total_seconds() / 60
    color = GREEN if mins <= 0 else RED if mins <= 30 else YELLOW if mins <= 60 else BLUE
    span = (END - START).total_seconds()
    ls, le = (datetime.combine(TODAY, t) for t in LUNCH)
    return {
        "start": f"{START:%H:%M}", "end": f"{END:%H:%M}", "remain": fmt_delta(left),
        "over": mins <= 0, "color": color,
        "ratio": min(max((now - START).total_seconds() / span, 0), 1),
        "lunch": ((ls - START).total_seconds() / span, (le - START).total_seconds() / span),
        "in_lunch": ls <= now < le,
    }


# ---------------- 版本們：fn(win) → update(view) ----------------

def variant_a(win):
    """現行版：橫向資訊列＋底部細進度線。"""
    row = tk.Frame(win, bg=BG, padx=12, pady=3)
    row.pack(fill="x")
    labels = {}
    for k, font in (("s_t", zh(9)), ("s_n", num(9)), ("e_t", zh(9)), ("e_n", num(9)),
                    ("r_t", zh(11, True)), ("r_n", num(13, True))):
        labels[k] = tk.Label(row, bg=BG, fg=SUBTEXT, font=font, padx=0)
    for k, gap in (("s_t", 0), ("s_n", 3), ("e_t", 12), ("e_n", 3), ("r_t", 12), ("r_n", 3)):
        labels[k].pack(side="left", padx=(gap, 0), anchor="s" if k.startswith("r") else "center")
    pc = tk.Canvas(win, width=1, height=3, bg=SURFACE, highlightthickness=0)
    pc.pack(fill="x")

    def update(v):
        labels["s_t"].config(text="上班"); labels["s_n"].config(text=v["start"])
        labels["e_t"].config(text="下班"); labels["e_n"].config(text=v["end"])
        labels["r_t"].config(text="可以下班了 +" if v["over"] else "剩", fg=v["color"])
        labels["r_n"].config(text=v["remain"], fg=v["color"])
        win.update_idletasks()
        pc.delete("all")
        pc.create_rectangle(0, 0, pc.winfo_width() * v["ratio"], 3, fill=v["color"], width=0)
    return update


def variant_b(win):
    """大字膠囊：只有倒數大字＋底色隨階段變色；滑鼠移上去才展開上下班時間。"""
    f = tk.Frame(win, padx=14, pady=1)
    f.pack()
    detail = tk.Label(f, font=num(10))
    big = tk.Label(f, font=num(18, True))
    big.pack(side="right")
    state = {"v": None}

    def paint():
        v = state["v"]
        tint = mix(v["color"], BG, 0.22)
        for w in (win, f, detail, big):
            w.config(bg=tint)
        big.config(fg=v["color"], text=("+" if v["over"] else "") + v["remain"])
        detail.config(fg=TEXT, text=f"{v['start']} → {v['end']}")

    def hover(on):
        if on:
            detail.pack(side="left", padx=(0, 10))
        else:
            detail.pack_forget()
        win.event_generate("<<Resized>>")

    def leave(_e):
        def chk():
            px, py = win.winfo_pointerxy()
            x, y = win.winfo_rootx(), win.winfo_rooty()
            hover(x <= px < x + win.winfo_width() and y <= py < y + win.winfo_height())
        win.after(80, chk)
    win.bind("<Enter>", lambda _e: hover(True))
    win.bind("<Leave>", leave)

    def update(v):
        state["v"] = v
        paint()
    return update


def variant_c(win):
    """整條就是進度條：背景填色＝已過時間，文字疊在上面。"""
    W, H = 290, 28
    cv = tk.Canvas(win, width=W, height=H, bg=SURFACE, highlightthickness=0)
    cv.pack()

    def update(v):
        cv.delete("all")
        cv.create_rectangle(0, 0, W * v["ratio"], H, fill=mix(v["color"], BG, 0.45), width=0)
        l0, l1 = v["lunch"]
        cv.create_rectangle(W * l0, H - 3, W * l1, H, fill=SUBTEXT, width=0)        # 午休段落
        cv.create_text(8, H / 2, text=v["start"], anchor="w", fill=mix(TEXT, BG, 0.7), font=num(9))
        cv.create_text(W - 8, H / 2, text=v["end"], anchor="e", fill=TEXT, font=num(9, True))
        mixed_text(cv, W / 2, H / 2, [("下班囉 +" if v["over"] else "剩 ", zh(10, True), "#ffffff"),
                                      (v["remain"], num(12, True), "#ffffff")], anchor="center")
    return update


def variant_d(win):
    """雙行卡片＋時間軸：上行上下班、下行巨大倒數、底部時間軸標出午休與現在位置。"""
    W, H = 230, 76
    cv = tk.Canvas(win, width=W, height=H, bg=BG, highlightthickness=0)
    cv.pack()

    def update(v):
        cv.delete("all")
        mixed_text(cv, 12, 13, [(v["start"], num(9), SUBTEXT), (" 上班  →  ", zh(9), SUBTEXT),
                                (v["end"], num(9, True), TEXT), (" 下班", zh(9), SUBTEXT)])
        cv.create_text(12, 39, anchor="w", fill=v["color"], font=num(22, True),
                       text=("+" if v["over"] else "") + v["remain"])
        cv.create_text(W - 12, 41, anchor="e", fill=SUBTEXT, font=zh(9),
                       text="已超時" if v["over"] else ("午休中" if v["in_lunch"] else "剩餘"))
        x0, x1, y = 12, W - 12, 64
        cv.create_line(x0, y, x1, y, fill=SURFACE, width=5, capstyle="round")
        nx = x0 + (x1 - x0) * v["ratio"]
        cv.create_line(x0, y, nx, y, fill=v["color"], width=5, capstyle="round")
        l0, l1 = v["lunch"]
        cv.create_line(x0 + (x1 - x0) * l0, y, x0 + (x1 - x0) * l1, y, fill=SUBTEXT, width=5, stipple="gray50")
        cv.create_oval(nx - 5, y - 5, nx + 5, y + 5, fill=TEXT, outline=BG, width=2)
    return update


KEY = "#010203"


def variant_e(win):
    """圓環小工具：圓形視窗，外環＝進度，中心＝倒數。"""
    S = 96
    win.config(bg=KEY)
    win.attributes("-transparentcolor", KEY)
    cv = tk.Canvas(win, width=S, height=S, bg=KEY, highlightthickness=0)
    cv.pack()

    def update(v):
        cv.delete("all")
        cv.create_oval(2, 2, S - 2, S - 2, fill=BG, outline="")
        box = (9, 9, S - 9, S - 9)
        cv.create_oval(*box, outline=SURFACE, width=7)
        if v["ratio"] >= 0.999:                 # tk 畫接近 360° 的 arc 會消失，滿格直接畫圓
            cv.create_oval(*box, outline=v["color"], width=7)
        elif v["ratio"] > 0:
            cv.create_arc(*box, start=90, extent=-359.9 * v["ratio"], style="arc", outline=v["color"], width=7)
        cv.create_text(S / 2, S / 2 - 6, text=("+" if v["over"] else "") + v["remain"],
                       fill=v["color"], font=num(14, True))
        mixed_text(cv, S / 2, S / 2 + 15, [("下班 ", zh(7), SUBTEXT), (v["end"], num(8), SUBTEXT)], anchor="center")
    return update


VARIANTS = [
    ("A", "現行版：橫向資訊列", variant_a),
    ("B", "大字膠囊（移上去才展開）", variant_b),
    ("C", "整條就是進度條", variant_c),
    ("D", "雙行卡片＋時間軸", variant_d),
    ("E", "圓環小工具", variant_e),
]


# ---------------- 切換器（白色膠囊，刻意跟設計本身做出區隔） ----------------

PILL = "#f5f5f5"


def build_switcher(root, groups, hint):
    """groups=[(標題, prev_fn, next_fn, 寬度)] → 回傳 (Toplevel, [label...])"""
    sw = tk.Toplevel(root)
    sw.overrideredirect(True)
    sw.attributes("-topmost", True)
    sw.configure(bg=PILL)
    f = tk.Frame(sw, bg=PILL, padx=10, pady=4)
    f.pack()
    ui = ("Microsoft JhengHei UI", 10)

    def btn(text, cmd):
        b = tk.Label(f, text=text, bg=PILL, fg="#111", font=(ui[0], 11, "bold"), cursor="hand2", padx=5)
        b.bind("<Button-1>", lambda _e: cmd())
        b.pack(side="left")
        return b
    labels = []
    for i, (title, prev, nxt, width) in enumerate(groups):
        if title:
            tk.Label(f, text=("｜" if i else "") + title, bg=PILL, fg="#666", font=(ui[0], 9)).pack(side="left", padx=(6, 0))
        btn("◀", prev)
        lbl = tk.Label(f, bg=PILL, fg="#111", font=(ui[0], 10, "bold"), width=width)
        lbl.pack(side="left")
        labels.append(lbl)
        btn("▶", nxt)
    btn("✕", root.destroy).pack_configure(padx=(12, 0))
    tk.Label(sw, text="PROTOTYPE ・ " + hint, bg=PILL, fg="#888", font=(ui[0], 8)).pack(pady=(0, 3))
    sw.update_idletasks()
    wa = monitor_rect(0, 0, work=True) or (0, 0, sw.winfo_screenwidth(), sw.winfo_screenheight())
    w, h = sw.winfo_reqwidth(), sw.winfo_reqheight()
    sw.geometry(f"+{(wa[0] + wa[2] - w) // 2}+{wa[3] - h - 16}")
    round_corners(sw)
    sw.bind("<Button-1>", lambda _e: sw.focus_force(), add="+")
    sw.after(200, sw.focus_force)
    return sw, labels


class Proto:
    def __init__(self, vi):
        self.root = tk.Tk()
        self.root.withdraw()
        self.vi, self.si, self.bar = vi, 0, None
        self.wa = monitor_rect(0, 0, work=True) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.sw, (self.lbl_v, self.lbl_s, self.lbl_f) = build_switcher(self.root, [
            ("版本", lambda: self.cycle_variant(-1), lambda: self.cycle_variant(1), 22),
            ("情境", lambda: self.cycle_scenario(-1), lambda: self.cycle_scenario(1), 15),
            ("字型", lambda: self.cycle_font(-1), lambda: self.cycle_font(1), 26),
        ], "←/→ 版本　↑/↓ 情境　F 字型　Esc 結束")
        for seq, fn in (("<Left>", lambda: self.cycle_variant(-1)), ("<Right>", lambda: self.cycle_variant(1)),
                        ("<Up>", lambda: self.cycle_scenario(-1)), ("<Down>", lambda: self.cycle_scenario(1)),
                        ("<f>", lambda: self.cycle_font(1)), ("<F>", lambda: self.cycle_font(-1)),
                        ("<Escape>", self.root.destroy)):
            self.root.bind_all(seq, lambda _e, f=fn: f())
        self._show_variant()
        self._tick()

    def _show_variant(self):
        if self.bar:
            self.bar.destroy()
        key, name, fn = VARIANTS[self.vi]
        w = self.bar = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=BG)
        self.update_fn = fn(w)
        w.bind("<<Resized>>", lambda _e: self._place())
        w.bind("<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.x_root - w.winfo_x(), e.y_root - w.winfo_y())))
        w.bind("<B1-Motion>", lambda e: w.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}"))
        self.lbl_v.config(text=f"{key} · {name}")
        self.lbl_f.config(text=FONTSETS[FS["i"]][0])
        self._render()
        if key != "E":
            round_corners(w)

    def _place(self):
        w = self.bar
        w.update_idletasks()
        bw, bh = w.winfo_reqwidth(), w.winfo_reqheight()
        w.geometry(f"+{self.wa[2] - 12 - bw}+{self.wa[3] - 8 - bh}")    # 跟正式版預設一樣：右下角錨點

    def _render(self):
        label, now = SCENARIOS[self.si]
        v = make_view(now or datetime.now())
        self.update_fn(v)
        self._place()
        self.lbl_s.config(text=label)
        key, name, _ = VARIANTS[self.vi]
        print(f"[{key} {name}] [{label}] [{FONTSETS[FS['i']][0]}] remain={v['remain']} "
              f"color={v['color']} ratio={v['ratio']:.2f} lunch={v['in_lunch']}")

    def cycle_variant(self, d):
        self.vi = (self.vi + d) % len(VARIANTS)
        self._show_variant()

    def cycle_scenario(self, d):
        self.si = (self.si + d) % len(SCENARIOS)
        self._render()

    def cycle_font(self, d):
        FS["i"] = (FS["i"] + d) % len(FONTSETS)
        self._show_variant()                     # 字型寫在元件建構時，直接重建

    def _tick(self):
        if SCENARIOS[self.si][1] is None:      # 實際時間情境才需要每秒更新
            self.update_fn(make_view(datetime.now()))
        for w in (self.bar, self.sw):
            force_topmost(w)
        self.root.after(1000, self._tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="A", choices=[k for k, _n, _f in VARIANTS])
    ap.add_argument("--font", type=int, default=0, choices=range(len(FONTSETS)))
    args = ap.parse_args()
    FS["i"] = args.font
    Proto([k for k, _n, _f in VARIANTS].index(args.variant)).run()
