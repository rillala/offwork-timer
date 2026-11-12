"""下班時間計算：從上班時間起算 N 小時，午休時段不計入。"""
from datetime import datetime, time, timedelta


def parse_hhmm(s: str) -> time:
    """接受 08:42、8:42、08：42（全形冒號）、0842、842。格式錯誤丟 ValueError。"""
    s = s.strip().replace("：", ":")
    if ":" in s:
        h, m = s.split(":")
    elif s.isdigit() and len(s) in (3, 4):
        h, m = s[:-2], s[-2:]
    else:
        raise ValueError(f"bad time: {s!r}")
    return time(int(h), int(m))


def calc_off_time(start: datetime, work_hours: float = 8,
                  lunch_start: time = time(12, 0),
                  lunch_end: time = time(13, 30)) -> datetime:
    day = start.date()
    ls = datetime.combine(day, lunch_start)
    le = datetime.combine(day, lunch_end)
    if ls <= start < le:          # 午休中打卡 → 從午休結束起算
        start = le
    end = start + timedelta(hours=work_hours)
    if start < ls < end:          # 工作區間跨過午休 → 補回午休長度
        end += le - ls
    return end


def fmt_delta(td: timedelta) -> str:
    """格式 HH:MM。倒數時分鐘無條件進位（最後一分鐘顯示 00:01）；超時則捨去。"""
    secs = int(td.total_seconds())
    mins = -(-secs // 60) if secs > 0 else -secs // 60
    h, m = divmod(mins, 60)
    return f"{h:02d}:{m:02d}"
