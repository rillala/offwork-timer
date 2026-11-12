"""共用的顏色、字型與繪圖小工具。

字型：中文一律微軟正黑體 UI；數字／英文用 Segoe UI Variable Display（Win11 內建），
Win10 沒有時由 resolve_fonts() 退回 Segoe UI。其他模組請用 zh() / num() 取字型，
不要 import FONT_NUM 常數（resolve 之後才會確定）。
"""
import tkinter.font as tkfont

BG, SURFACE, HOVER = "#1e1e2e", "#313244", "#45475a"
TEXT, SUBTEXT = "#cdd6f4", "#7f849c"
BLUE, YELLOW, RED, GREEN = "#4cc9f0", "#ffd166", "#ff4d6d", "#06d6a0"
GRAY = "#888888"
COLORS = ["#ff4d6d", "#ffd166", "#06d6a0", "#4cc9f0", "#c77dff",
          "#ff9f1c", "#f72585", "#90e0ef", "#ffffff"]
KEY = "#010203"   # 透明色鍵

FONT_ZH = "Microsoft JhengHei UI"
_NUM_CANDIDATES = ("Segoe UI Variable Display", "Segoe UI", "Arial")
_font = {"num": _NUM_CANDIDATES[0]}


def resolve_fonts(root):
    """Tk 建立後呼叫一次：挑出這台電腦上有的數字字型。"""
    fams = set(tkfont.families(root))
    _font["num"] = next((f for f in _NUM_CANDIDATES if f in fams), "TkDefaultFont")
    return _font["num"]


def num_family():
    return _font["num"]


def zh(size, bold=False):
    return (FONT_ZH, size, "bold" if bold else "normal")


def num(size, bold=False):
    return (_font["num"], size, "bold" if bold else "normal")


def mix(c1, c2, t):
    """c1 與 c2 混色，t=1 → 全 c1。"""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(a, b))


def mixed_text(cv, x, y, parts, anchor="w"):
    """在 Canvas 上中英混排：parts=[(文字, font, 顏色), ...]；anchor 為 w / center / e。"""
    widths = [tkfont.Font(font=f).measure(t) for t, f, _c in parts]
    total = sum(widths)
    x0 = x - total / 2 if anchor == "center" else x - total if anchor == "e" else x
    for (t, f, c), w in zip(parts, widths):
        cv.create_text(x0, y, text=t, font=f, fill=c, anchor="w")
        x0 += w


def remind_parts(minutes, zh_size, num_size, color):
    """「再 N 分鐘下班！」的中英混排片段。"""
    return [("再 ", zh(zh_size, True), color), (str(minutes), num(num_size, True), color),
            (" 分鐘下班！", zh(zh_size, True), color)]
