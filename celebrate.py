"""全螢幕煙火 + 彩帶特效（透明、滑鼠穿透、數秒後自動消失）。"""
import ctypes
import math
import random
import sys
import tkinter as tk

KEY = "#010203"  # 透明色鍵
COLORS = ["#ff4d6d", "#ffd166", "#06d6a0", "#4cc9f0", "#c77dff",
          "#ff9f1c", "#f72585", "#90e0ef", "#ffffff"]
FPS = 33
GRAVITY = 0.12


def _click_through(win: tk.Toplevel):
    if sys.platform != "win32":
        return
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)


class Celebration:
    def __init__(self, root: tk.Tk, message: str, duration_ms: int = 9000):
        self.root = root
        self.w = root.winfo_screenwidth()
        self.h = root.winfo_screenheight()
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{self.w}x{self.h}+0+0")
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            self.win.attributes("-alpha", 0.85)
        self.cv = tk.Canvas(self.win, bg=KEY, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.win.update_idletasks()
        _click_through(self.win)

        self.message = message
        self.confetti = [self._new_confetti(initial=True) for _ in range(160)]
        self.rockets, self.sparks = [], []
        self.frame = 0
        self.total_frames = duration_ms // FPS
        self.alive = True
        self._tick()

    # ---------- particles ----------
    def _new_confetti(self, initial=False):
        return {
            "x": random.uniform(0, self.w),
            "y": random.uniform(-self.h, 0) if initial else random.uniform(-80, -10),
            "vy": random.uniform(2, 5), "vx": random.uniform(-1, 1),
            "a": random.uniform(0, math.pi), "va": random.uniform(-0.2, 0.2),
            "sway": random.uniform(0, math.tau), "size": random.uniform(6, 12),
            "c": random.choice(COLORS),
        }

    def _launch(self):
        self.rockets.append({
            "x": random.uniform(self.w * 0.15, self.w * 0.85), "y": self.h,
            "vx": random.uniform(-1.5, 1.5), "vy": -random.uniform(13, 18),
            "c": random.choice(COLORS),
        })

    def _explode(self, r):
        n = random.randint(50, 80)
        speed = random.uniform(4, 7)
        for i in range(n):
            ang = math.tau * i / n
            sp = speed * random.uniform(0.6, 1.0)
            self.sparks.append({"x": r["x"], "y": r["y"],
                                "vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp,
                                "life": random.randint(35, 55), "c": r["c"]})

    # ---------- loop ----------
    def _tick(self):
        if not self.alive:
            return
        self.frame += 1
        ending = self.frame > self.total_frames - 60
        cv = self.cv
        cv.delete("all")

        if not ending and self.frame % 18 == 0:
            self._launch()

        for r in self.rockets[:]:
            r["x"] += r["vx"]; r["y"] += r["vy"]; r["vy"] += GRAVITY * 1.5
            cv.create_oval(r["x"] - 3, r["y"] - 3, r["x"] + 3, r["y"] + 3, fill=r["c"], outline="")
            if r["vy"] >= -1:
                self.rockets.remove(r)
                self._explode(r)

        for s in self.sparks[:]:
            s["x"] += s["vx"]; s["y"] += s["vy"]
            s["vx"] *= 0.97; s["vy"] = s["vy"] * 0.97 + GRAVITY
            s["life"] -= 1
            if s["life"] <= 0:
                self.sparks.remove(s); continue
            rad = max(1, s["life"] / 14)
            cv.create_oval(s["x"] - rad, s["y"] - rad, s["x"] + rad, s["y"] + rad, fill=s["c"], outline="")

        for c in self.confetti:
            c["sway"] += 0.05; c["a"] += c["va"]
            c["x"] += c["vx"] + math.sin(c["sway"]); c["y"] += c["vy"]
            if c["y"] > self.h + 20 and not ending:
                c.update(self._new_confetti())
            sz, a = c["size"], c["a"]
            dx, dy = math.cos(a) * sz, math.sin(a) * sz * 0.5
            px, py = -math.sin(a) * sz * 0.35, math.cos(a) * sz * 0.35
            cv.create_polygon(c["x"] - dx - px, c["y"] - dy - py, c["x"] + dx - px, c["y"] + dy - py,
                              c["x"] + dx + px, c["y"] + dy + py, c["x"] - dx + px, c["y"] - dy + py,
                              fill=c["c"], outline="")

        # 中央訊息（先畫陰影再畫字）
        fs = 54
        cx, cy = self.w // 2, int(self.h * 0.4)
        for ox, oy in ((3, 3), (-2, 2), (2, -2)):
            cv.create_text(cx + ox, cy + oy, text=self.message, fill="#222222",
                           font=("Microsoft JhengHei UI", fs, "bold"))
        cv.create_text(cx, cy, text=self.message, fill="#ffd166",
                       font=("Microsoft JhengHei UI", fs, "bold"))

        if self.frame >= self.total_frames:
            self.close(); return
        self.win.after(FPS, self._tick)

    def close(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
