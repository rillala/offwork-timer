"""下班前提示畫面：煙火＋邊緣光暈／右下角通知卡／頂部橫幅。

全部是透明（或半透明）、滑鼠可穿透、時間到自動消失的視窗，不會擋住工作。
動畫依實際經過時間推進（Windows 的 after() 常比設定的間隔慢，用累加幀數會讓動畫越拖越長）。
"""
import ctypes
import math
import random
import sys
import time
import tkinter as tk

from theme import BG, COLORS, KEY, SUBTEXT, SURFACE, TEXT, YELLOW, mix, mixed_text, num, remind_parts, zh

FPS = 33          # 每幀毫秒數
GRAVITY = 0.12


def _click_through(win: tk.Toplevel):
    if sys.platform != "win32":
        return
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)


def _ease_out(t):
    t = min(max(t, 0), 1)
    return 1 - (1 - t) ** 3


def _rrect(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


class Overlay:
    """滑鼠穿透、會自己消失的動畫視窗。子類別實作 step(frame)（模擬）與 draw(frame)（繪圖）。"""
    seconds = 7

    def __init__(self, root, x, y, w, h, transparent=True):
        self.w, self.h = w, h
        win = self.win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")
        if transparent:
            try:
                win.attributes("-transparentcolor", KEY)
            except tk.TclError:
                win.attributes("-alpha", 0.85)
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
        target = min(self.total, max(self.frame + 1, int((time.monotonic() - self.t0) * 1000 / FPS)))
        while self.frame < target:              # 落後時補跑模擬，維持物理速度
            self.frame += 1
            self.step(self.frame)
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

    def step(self, f):
        pass

    def draw(self, f):
        raise NotImplementedError


class Fireworks(Overlay):
    """全螢幕煙火＋彩帶＋四邊彩色光帶，中央大字（中文正黑體、數字 Segoe UI Variable）。"""
    seconds = 9

    def __init__(self, root, minutes, mon):
        self.minutes = minutes
        self.mw, self.mh = mon[2] - mon[0], mon[3] - mon[1]
        self.confetti = [self._new_confetti(initial=True) for _ in range(160)]
        self.rockets, self.sparks = [], []
        super().__init__(root, mon[0], mon[1], self.mw, self.mh)

    def _new_confetti(self, initial=False):
        return {"x": random.uniform(0, self.mw),
                "y": random.uniform(-self.mh, 0) if initial else random.uniform(-80, -10),
                "vy": random.uniform(2, 5), "vx": random.uniform(-1, 1),
                "a": random.uniform(0, math.pi), "va": random.uniform(-0.2, 0.2),
                "sway": random.uniform(0, math.tau), "size": random.uniform(6, 12),
                "c": random.choice(COLORS)}

    def step(self, f):
        W, H = self.w, self.h
        ending = f > self.total - 60
        if not ending and f % 18 == 0:
            self.rockets.append({"x": random.uniform(W * 0.15, W * 0.85), "y": H,
                                 "vx": random.uniform(-1.5, 1.5), "vy": -random.uniform(13, 18),
                                 "c": random.choice(COLORS)})
        for r in self.rockets[:]:
            r["x"] += r["vx"]; r["y"] += r["vy"]; r["vy"] += GRAVITY * 1.5
            if r["vy"] >= -1:
                self.rockets.remove(r)
                n, speed = random.randint(50, 80), random.uniform(4, 7)
                for i in range(n):
                    ang, sp = math.tau * i / n, speed * random.uniform(0.6, 1.0)
                    self.sparks.append({"x": r["x"], "y": r["y"], "vx": math.cos(ang) * sp,
                                        "vy": math.sin(ang) * sp, "life": random.randint(35, 55), "c": r["c"]})
        for s in self.sparks[:]:
            s["x"] += s["vx"]; s["y"] += s["vy"]
            s["vx"] *= 0.97; s["vy"] = s["vy"] * 0.97 + GRAVITY
            s["life"] -= 1
            if s["life"] <= 0:
                self.sparks.remove(s)
        for c in self.confetti:
            c["sway"] += 0.05; c["a"] += c["va"]
            c["x"] += c["vx"] + math.sin(c["sway"]); c["y"] += c["vy"]
            if c["y"] > H + 20 and not ending:
                c.update(self._new_confetti())

    def _draw_edges(self, f):
        cv, W, H = self.cv, self.w, self.h
        fade = min(1, f / 10, (self.total - f) / 15)
        t = (8 + 6 * math.sin(f * 0.18)) * fade
        if t <= 0.5:
            return
        seg, shift = 90, f * 4
        for edge in range(4):
            length = W if edge % 2 == 0 else H
            for i in range(-1, length // seg + 2):
                a = i * seg + shift % seg
                b = a + seg
                c = COLORS[(i - shift // seg + edge * 3) % len(COLORS)]
                if edge == 0:
                    cv.create_rectangle(a, 0, b, t, fill=c, width=0)
                elif edge == 1:
                    cv.create_rectangle(W - t, a, W, b, fill=c, width=0)
                elif edge == 2:
                    cv.create_rectangle(W - b, H - t, W - a, H, fill=c, width=0)
                else:
                    cv.create_rectangle(0, H - b, t, H - a, fill=c, width=0)

    def draw(self, f):
        cv = self.cv
        self._draw_edges(f)
        for r in self.rockets:
            cv.create_oval(r["x"] - 3, r["y"] - 3, r["x"] + 3, r["y"] + 3, fill=r["c"], outline="")
        for s in self.sparks:
            rad = max(1, s["life"] / 14)
            cv.create_oval(s["x"] - rad, s["y"] - rad, s["x"] + rad, s["y"] + rad, fill=s["c"], outline="")
        for c in self.confetti:
            sz, a = c["size"], c["a"]
            dx, dy = math.cos(a) * sz, math.sin(a) * sz * 0.5
            px, py = -math.sin(a) * sz * 0.35, math.cos(a) * sz * 0.35
            cv.create_polygon(c["x"] - dx - px, c["y"] - dy - py, c["x"] + dx - px, c["y"] + dy - py,
                              c["x"] + dx + px, c["y"] + dy + py, c["x"] - dx + px, c["y"] - dy + py,
                              fill=c["c"], outline="")
        cx, cy = self.w / 2, self.h * 0.4
        for ox, oy in ((3, 3), (-2, 2), (2, -2)):                     # 先畫陰影再畫字
            mixed_text(cv, cx + ox, cy + oy, remind_parts(self.minutes, 54, 62, "#222222"), anchor="center")
        mixed_text(cv, cx, cy, remind_parts(self.minutes, 54, 62, YELLOW), anchor="center")


class Toast(Overlay):
    """右下角通知卡：從右側滑入、上緣噴一小團彩帶、底部有自動關閉倒數線。貼在浮動條上方。"""
    W, H, CW, CH = 460, 330, 360, 112

    def __init__(self, root, minutes, end_str, work, bar_rect=None):
        self.minutes, self.end_str, self.parts = minutes, end_str, []
        if bar_rect:                       # 卡片右緣對齊浮動條右緣、底部在浮動條上方
            right, bottom = bar_rect[2], bar_rect[1] - 8
        else:
            right, bottom = work[2] - 8, work[3] - 56
        x = min(max(right - self.W, work[0]), work[2] - self.W)
        y = min(max(bottom - self.H, work[1]), work[3] - self.H)
        super().__init__(root, x, y, self.W, self.H)

    def _card_x(self, f):
        slide = _ease_out(f / 14) if f < self.total - 14 else _ease_out((self.total - f) / 14)
        return self.W - 4 - self.CW + (1 - slide) * (self.CW + 20)

    def step(self, f):
        if f == 14:
            x0, y0 = self._card_x(f), self.H - self.CH - 4
            for _ in range(70):
                self.parts.append({"x": x0 + self.CW / 2 + random.uniform(-self.CW / 3, self.CW / 3), "y": y0,
                                   "vx": random.uniform(-3.5, 3.5), "vy": -random.uniform(5, 11),
                                   "c": random.choice(COLORS), "s": random.uniform(3, 6), "life": 70})
        for p in self.parts[:]:
            p["x"] += p["vx"]; p["y"] += p["vy"]; p["vy"] += 0.35; p["vx"] *= 0.98; p["life"] -= 1
            if p["life"] <= 0 or p["y"] > self.H:
                self.parts.remove(p)

    def draw(self, f):
        cv, cw, ch = self.cv, self.CW, self.CH
        for p in self.parts:
            s = p["s"]
            cv.create_rectangle(p["x"] - s, p["y"] - s / 2, p["x"] + s, p["y"] + s / 2, fill=p["c"], width=0)
        x0, y0 = self._card_x(f), self.H - ch - 4
        _rrect(cv, x0, y0, x0 + cw, y0 + ch, 18, fill=BG, outline=YELLOW, width=2)
        cv.create_rectangle(x0 + 2, y0 + 18, x0 + 7, y0 + ch - 18, fill=YELLOW, width=0)
        mixed_text(cv, x0 + 22, y0 + 36, remind_parts(self.minutes, 16, 20, YELLOW))
        mixed_text(cv, x0 + 22, y0 + 72, [(self.end_str, num(11, True), TEXT),
                                          (" 下班・記得存檔、收桌面", zh(10), SUBTEXT)])
        left = 1 - f / self.total
        cv.create_line(x0 + 22, y0 + ch - 16, x0 + 22 + (cw - 44) * left, y0 + ch - 16, fill=SURFACE, width=3)


class Banner(Overlay):
    """頂部全寬橫幅：從上方滑下，右側 mm:ss 實際倒數，背景閃爍小星星。"""
    BH = 76

    def __init__(self, root, minutes, end_str, mon):
        self.minutes, self.end_str = minutes, end_str
        self.mx, self.my = mon[0], mon[1]
        W = mon[2] - mon[0]
        self.stars = [(random.uniform(0, W), random.uniform(8, self.BH - 10), random.uniform(0, math.tau),
                       random.choice(COLORS)) for _ in range(40)]
        super().__init__(root, self.mx, self.my - self.BH, W, self.BH, transparent=False)

    def draw(self, f):
        cv, W, H = self.cv, self.w, self.h
        slide = _ease_out(f / 12) if f < self.total - 12 else _ease_out((self.total - f) / 12)
        self.win.geometry(f"+{self.mx}+{self.my - H + int(H * slide)}")
        cv.create_rectangle(0, 0, W, H, fill=mix(YELLOW, BG, 0.16), width=0)
        cv.create_rectangle(0, H - 3, W, H, fill=YELLOW, width=0)
        for x, y, ph, c in self.stars:
            r = 2 + 3 * max(0, math.sin(f * 0.18 + ph))
            cv.create_polygon(x, y - r * 2, x + r / 2, y - r / 2, x + r * 2, y, x + r / 2, y + r / 2,
                              x, y + r * 2, x - r / 2, y + r / 2, x - r * 2, y, x - r / 2, y - r / 2,
                              fill=c, outline="")
        mixed_text(cv, 40, H / 2 - 2, remind_parts(self.minutes, 18, 22, YELLOW) +
                   [("   ", zh(10), TEXT), (self.end_str, num(12, True), TEXT), (" 下班", zh(11), SUBTEXT)])
        secs = max(0, self.minutes * 60 - f * FPS // 1000)
        cv.create_text(W - 40, H / 2 - 2, anchor="e", text=f"{secs // 60:02d}:{secs % 60:02d}",
                       fill=TEXT, font=num(24, True))


def play(root, style, minutes, end_str, mon, work, bar_rect=None):
    """播放提示畫面。mon / work：浮動條所在螢幕的完整範圍與工作區 (l, t, r, b)。"""
    if style == "toast":
        return Toast(root, minutes, end_str, work, bar_rect)
    if style == "banner":
        return Banner(root, minutes, end_str, mon)
    return Fireworks(root, minutes, mon)
