"""PROTOTYPE（用完即丟，不要合進正式程式）——下班前提示畫面該長什麼樣子？

4 個結構不同的提示版本，全部滑鼠可穿透、自動消失。
底部白色切換列：←/→ 版本（切換時自動播放）、空白鍵 重播、F 字型、Esc 結束。
執行：python prototype_celebrate.py [--variant B] [--font 2]
字型組合與浮動條原型共用（prototype_bar.FONTSETS）；版本 A 是正式版原樣，字型寫死、不受 F 影響。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 專案根目錄
import argparse
import math
import random
import time
import tkinter as tk

import prototype_bar as pb
from app import force_topmost, monitor_rect
from celebrate import COLORS, Fireworks, _click_through
from theme import BG, SUBTEXT, SURFACE, TEXT, YELLOW
from prototype_bar import FONTSETS, FS, mix, mixed_text, num, zh

KEY = "#010203"
FPS = 33
REMIND_MIN = 10
END = f"{pb.END:%H:%M}"


def rrect(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


def ease_out(t):
    t = min(max(t, 0), 1)
    return 1 - (1 - t) ** 3


class Overlay:
    """透明、滑鼠穿透、會自己消失的動畫視窗。子類別實作 draw(frame)。"""
    seconds = 7

    def __init__(self, root, x, y, w, h, transparent=True):
        self.w, self.h = w, h
        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")
        if transparent:
            win.attributes("-transparentcolor", KEY)
        else:
            win.attributes("-alpha", 0.97)          # 讓視窗變 layered，滑鼠穿透才有效
        self.cv = tk.Canvas(win, bg=KEY if transparent else BG, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        win.update_idletasks()
        _click_through(win)
        self.frame, self.total = 0, self.seconds * 1000 // FPS
        self.t0 = time.monotonic()
        self.alive = True
        self._tick()

    def _tick(self):
        if not self.alive:
            return
        # 依實際經過時間換算幀數：Windows 的 after() 常比 33ms 慢，用累加會讓動畫越拖越長
        self.frame = max(self.frame + 1, int((time.monotonic() - self.t0) * 1000 / FPS))
        self.cv.delete("all")
        self.draw(self.frame)
        if self.frame >= self.total:
            self.close()
            return
        self.win.after(FPS, self._tick)

    def close(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def draw(self, f):
        raise NotImplementedError


class Toast(Overlay):
    """B：右下角通知卡，從右側滑入，卡片上緣噴出一小團彩帶，底部倒數線。"""
    def __init__(self, root):
        wa = monitor_rect(0, 0, work=True)
        W, H = 460, 330
        self.parts = []
        super().__init__(root, wa[2] - W - 8, wa[3] - H - 56, W, H)    # 56：留給浮動條

    def draw(self, f):
        cv, W, H = self.cv, self.w, self.h
        cw, ch = 360, 112
        slide = ease_out(f / 14) if f < self.total - 14 else ease_out((self.total - f) / 14)
        x0 = W - 4 - cw + (1 - slide) * (cw + 20)
        y0 = H - ch - 4
        if f == 14:
            for _ in range(70):
                self.parts.append({"x": x0 + cw / 2 + random.uniform(-cw / 3, cw / 3), "y": y0,
                                   "vx": random.uniform(-3.5, 3.5), "vy": -random.uniform(5, 11),
                                   "c": random.choice(COLORS), "s": random.uniform(3, 6), "life": 70})
        for p in self.parts[:]:
            p["x"] += p["vx"]; p["y"] += p["vy"]; p["vy"] += 0.35; p["vx"] *= 0.98; p["life"] -= 1
            if p["life"] <= 0 or p["y"] > H:
                self.parts.remove(p); continue
            s = p["s"]
            cv.create_rectangle(p["x"] - s, p["y"] - s / 2, p["x"] + s, p["y"] + s / 2, fill=p["c"], width=0)
        rrect(cv, x0, y0, x0 + cw, y0 + ch, 18, fill=BG, outline=YELLOW, width=2)
        cv.create_rectangle(x0 + 2, y0 + 18, x0 + 7, y0 + ch - 18, fill=YELLOW, width=0)
        mixed_text(cv, x0 + 22, y0 + 36, [("再 ", zh(16, True), YELLOW), (str(REMIND_MIN), num(22, True), YELLOW),
                                          (" 分鐘下班！", zh(16, True), YELLOW)])
        mixed_text(cv, x0 + 22, y0 + 72, [(END, num(11, True), TEXT), (" 下班・記得存檔、收桌面", zh(10), SUBTEXT)])
        left = 1 - f / self.total
        cv.create_line(x0 + 22, y0 + ch - 16, x0 + 22 + (cw - 44) * left, y0 + ch - 16, fill=SURFACE, width=3)


class Banner(Overlay):
    """C：頂部全寬橫幅，從上方滑下，右側實際倒數，背景閃爍小星星。"""
    def __init__(self, root):
        mon = monitor_rect(0, 0)
        self.mx, self.my = mon[0], mon[1]
        W, H = mon[2] - mon[0], 76
        self.stars = [(random.uniform(0, W), random.uniform(8, H - 10), random.uniform(0, math.tau),
                       random.choice(COLORS)) for _ in range(40)]
        super().__init__(root, self.mx, self.my - H, W, H, transparent=False)

    def draw(self, f):
        cv, W, H = self.cv, self.w, self.h
        slide = ease_out(f / 12) if f < self.total - 12 else ease_out((self.total - f) / 12)
        self.win.geometry(f"+{self.mx}+{self.my - H + int(H * slide)}")
        cv.create_rectangle(0, 0, W, H, fill=mix(YELLOW, BG, 0.16), width=0)
        cv.create_rectangle(0, H - 3, W, H, fill=YELLOW, width=0)
        for x, y, ph, c in self.stars:
            r = 2 + 3 * max(0, math.sin(f * 0.18 + ph))
            cv.create_polygon(x, y - r * 2, x + r / 2, y - r / 2, x + r * 2, y, x + r / 2, y + r / 2,
                              x, y + r * 2, x - r / 2, y + r / 2, x - r * 2, y, x - r / 2, y - r / 2,
                              fill=c, outline="")
        mixed_text(cv, 40, H / 2 - 2, [("再 ", zh(18, True), YELLOW), (str(REMIND_MIN), num(24, True), YELLOW),
                                       (" 分鐘下班！", zh(18, True), YELLOW),
                                       ("   ", zh(10), TEXT), (END, num(12, True), TEXT), (" 下班", zh(11), SUBTEXT)])
        secs = max(0, REMIND_MIN * 60 - f * FPS // 1000)
        cv.create_text(W - 40, H / 2 - 2, anchor="e", text=f"{secs // 60:02d}:{secs % 60:02d}",
                       fill=TEXT, font=num(24, True))


class EdgeGlow(Overlay):
    """D：螢幕四邊彩色跑馬燈光帶脈動，中央大字彈出後收起；不遮擋畫面中央內容。"""
    seconds = 6

    def __init__(self, root):
        mon = monitor_rect(0, 0)
        super().__init__(root, mon[0], mon[1], mon[2] - mon[0], mon[3] - mon[1])

    def draw(self, f):
        cv, W, H = self.cv, self.w, self.h
        fade = min(1, f / 10, (self.total - f) / 15)
        t = (8 + 6 * math.sin(f * 0.18)) * fade
        seg = 90
        shift = f * 4
        for edge in range(4):
            length = W if edge % 2 == 0 else H
            for i in range(-1, length // seg + 2):
                a = i * seg + shift % seg
                b = a + seg
                c = COLORS[(i - shift // seg + edge * 3) % len(COLORS)]
                if edge == 0:   cv.create_rectangle(a, 0, b, t, fill=c, width=0)
                elif edge == 1: cv.create_rectangle(W - t, a, W, b, fill=c, width=0)
                elif edge == 2: cv.create_rectangle(W - b, H - t, W - a, H, fill=c, width=0)
                else:           cv.create_rectangle(0, H - b, t, H - a, fill=c, width=0)
        if f < 85:
            pop = ease_out(f / 10) if f < 70 else ease_out((85 - f) / 15)
            size = max(1, int(56 * pop))
            cx, cy = W / 2, H * 0.42
            for ox, oy in ((3, 3), (-2, 2), (2, -2)):
                mixed_text(cv, cx + ox, cy + oy, [("再 ", zh(size, True), "#222222"),
                                                  (str(REMIND_MIN), num(int(size * 1.3), True), "#222222"),
                                                  (" 分鐘下班！", zh(size, True), "#222222")], anchor="center")
            mixed_text(cv, cx, cy, [("再 ", zh(size, True), YELLOW), (str(REMIND_MIN), num(int(size * 1.3), True), YELLOW),
                                    (" 分鐘下班！", zh(size, True), YELLOW)], anchor="center")


VARIANTS = [
    ("A", "正式版：煙火＋彩帶＋邊緣光暈", lambda root: Fireworks(root, REMIND_MIN, monitor_rect(0, 0))),
    ("B", "右下角通知卡", Toast),
    ("C", "頂部橫幅＋倒數", Banner),
    ("D", "螢幕邊緣光暈", EdgeGlow),
]


class Proto:
    def __init__(self, vi):
        self.root = tk.Tk()
        self.root.withdraw()
        self.vi, self.fx = vi, None
        self.sw, (self.lbl_v, self.lbl_f) = pb.build_switcher(self.root, [
            ("版本", lambda: self.cycle(-1), lambda: self.cycle(1), 20),
            ("字型", lambda: self.cycle_font(-1), lambda: self.cycle_font(1), 26),
        ], "←/→ 版本　空白鍵 重播　F 字型　Esc 結束")
        for seq, fn in (("<Left>", lambda: self.cycle(-1)), ("<Right>", lambda: self.cycle(1)),
                        ("<space>", self.play), ("<f>", lambda: self.cycle_font(1)),
                        ("<F>", lambda: self.cycle_font(-1)), ("<Escape>", self.root.destroy)):
            self.root.bind_all(seq, lambda _e, f=fn: f())
        self.root.after(300, self.play)
        self._keep_top()

    def play(self):
        if self.fx and self.fx.alive:
            self.fx.close()
        key, name, factory = VARIANTS[self.vi]
        self.lbl_v.config(text=f"{key} · {name}")
        self.lbl_f.config(text=FONTSETS[FS["i"]][0])
        print(f"[{key} {name}] [{FONTSETS[FS['i']][0]}]")
        self.fx = factory(self.root)

    def cycle(self, d):
        self.vi = (self.vi + d) % len(VARIANTS)
        self.play()

    def cycle_font(self, d):
        FS["i"] = (FS["i"] + d) % len(FONTSETS)
        self.play()

    def _keep_top(self):
        force_topmost(self.sw)
        self.root.after(500, self._keep_top)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="A", choices=[k for k, _n, _f in VARIANTS])
    ap.add_argument("--font", type=int, default=0, choices=range(len(FONTSETS)))
    args = ap.parse_args()
    FS["i"] = args.font
    Proto([k for k, _n, _f in VARIANTS].index(args.variant)).run()
