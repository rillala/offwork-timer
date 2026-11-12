"""浮動條的四種樣式。由 App 建立在浮動條視窗裡；切換樣式時整個銷毀重建。

view（由 App 組出）：
    start / end / remain : "HH:MM" 字串
    over     : 是否已過下班時間
    color    : 依階段的顏色（藍／黃／紅／綠）
    ratio    : 當日進度 0～1
    lunch    : 午休在進度中的位置 (起, 迄)，0～1
    in_lunch : 現在是否午休中
"""
import tkinter as tk

from theme import BG, KEY, SUBTEXT, SURFACE, TEXT, mix, mixed_text, num, zh


class BarStyle:
    transparent = False      # True → 視窗用透明色鍵、不套圓角（圓環）

    def __init__(self, win, cfg):
        self.win, self.cfg = win, cfg
        self.frame = tk.Frame(win, bg=KEY if self.transparent else BG)
        self.frame.pack()
        self.build()

    def build(self):
        raise NotImplementedError

    def update(self, v):
        raise NotImplementedError

    def destroy(self):
        self.frame.destroy()


class RowStyle(BarStyle):
    """A 橫向資訊列：上班／下班小灰字＋剩餘時間大字＋底部細進度線。顯示項目可在設定勾選。"""

    def build(self):
        c = self.cfg
        row = tk.Frame(self.frame, bg=BG, padx=12, pady=3)
        row.pack(fill="x")

        def lbl(font, fg=SUBTEXT):
            return tk.Label(row, bg=BG, fg=fg, font=font, padx=0)
        self.s_t, self.s_n = lbl(zh(9)), lbl(num(9))
        self.e_t, self.e_n = lbl(zh(9)), lbl(num(9))
        self.r_t, self.r_n = lbl(zh(11, True)), lbl(num(13, True))
        groups = [g for g, on in (((self.s_t, self.s_n), c["show_start"]), ((self.e_t, self.e_n), c["show_end"]),
                                  ((self.r_t, self.r_n), c["show_remain"])) if on]
        for i, (t, n) in enumerate(groups):
            t.pack(side="left", padx=(0 if i == 0 else 12, 0))
            n.pack(side="left", padx=(3, 0))
        self.s_t.config(text="上班")
        self.e_t.config(text="下班")
        self.progress = None
        if c["show_progress"]:
            # width=1：別讓 Canvas 預設的 10cm 寬度撐開浮動條
            self.progress = tk.Canvas(self.frame, width=1, height=3, bg=SURFACE, highlightthickness=0, bd=0)
            self.progress.pack(fill="x")

    def update(self, v):
        self.s_n.config(text=v["start"])
        self.e_n.config(text=v["end"])
        self.r_t.config(text="可以下班了 +" if v["over"] else "剩", fg=v["color"])
        self.r_n.config(text=v["remain"], fg=v["color"])
        if self.progress:
            self.win.update_idletasks()
            self.progress.delete("all")
            self.progress.create_rectangle(0, 0, int(self.progress.winfo_width() * v["ratio"]), 3,
                                           fill=v["color"], width=0)


class CapsuleStyle(BarStyle):
    """B 大字膠囊：只顯示剩餘時間大字，底色隨階段變色。"""

    def build(self):
        self.big = tk.Label(self.frame, font=num(18, True), padx=14, pady=1)
        self.big.pack()

    def update(self, v):
        tint = mix(v["color"], BG, 0.22)
        self.frame.config(bg=tint)
        self.big.config(bg=tint, fg=v["color"], text=("+" if v["over"] else "") + v["remain"])


class CardStyle(BarStyle):
    """D 雙行卡片＋時間軸：上行上下班、下行大字倒數、底部時間軸標出午休與現在位置。"""
    W, H = 230, 76

    def build(self):
        self.cv = tk.Canvas(self.frame, width=self.W, height=self.H, bg=BG, highlightthickness=0)
        self.cv.pack()

    def update(self, v):
        cv, W = self.cv, self.W
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


class RingStyle(BarStyle):
    """E 圓環：圓形視窗，外環＝當日進度，中心＝倒數。"""
    transparent = True
    S = 96

    def build(self):
        self.cv = tk.Canvas(self.frame, width=self.S, height=self.S, bg=KEY, highlightthickness=0)
        self.cv.pack()

    def update(self, v):
        cv, S = self.cv, self.S
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


class UnsetStyle(BarStyle):
    """尚未設定上班時間：所有樣式共用。"""

    def build(self):
        tk.Label(self.frame, text="尚未設定上班時間（雙擊設定）", fg=TEXT, bg=BG,
                 font=zh(10), padx=12, pady=4).pack()

    def update(self, v):
        pass


STYLES = {"row": RowStyle, "capsule": CapsuleStyle, "card": CardStyle, "ring": RingStyle}
