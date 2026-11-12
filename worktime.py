"""下班時間計算：從上班時間起算 N 小時，午休時段不計入。"""
from datetime import datetime, time, timedelta


def parse_hhmm(s: str) -> time:
    h, m = s.strip().split(":")
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
