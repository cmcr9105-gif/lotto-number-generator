
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd

DEFAULT_DB = "lotto_app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    draw_no INTEGER PRIMARY KEY,
    draw_date TEXT,
    n1 INTEGER NOT NULL,
    n2 INTEGER NOT NULL,
    n3 INTEGER NOT NULL,
    n4 INTEGER NOT NULL,
    n5 INTEGER NOT NULL,
    n6 INTEGER NOT NULL,
    bonus INTEGER NOT NULL,
    source TEXT DEFAULT 'manual',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_draw INTEGER,
    strategy TEXT NOT NULL,
    numbers TEXT NOT NULL,
    score REAL,
    birth_mode INTEGER DEFAULT 0,
    include_numbers TEXT,
    exclude_numbers TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS match_results (
    recommendation_id INTEGER PRIMARY KEY,
    target_draw INTEGER NOT NULL,
    main_hits INTEGER NOT NULL,
    bonus_hit INTEGER NOT NULL DEFAULT 0,
    prize_rank INTEGER,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(recommendation_id) REFERENCES recommendations(id)
);
CREATE INDEX IF NOT EXISTS idx_rec_target_draw ON recommendations(target_draw);
CREATE INDEX IF NOT EXISTS idx_rec_strategy ON recommendations(strategy);
"""

def connect(db_path=DEFAULT_DB):
    """Open an ordinary DB connection only.

    IMPORTANT: Do not create schema or change journal mode here. Streamlit reruns
    the script on widget interaction; doing DDL/PRAGMA journal changes on every
    read connection can cause unnecessary locks and instability.
    """
    con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    return con

def init_db(db_path=DEFAULT_DB):
    """Create/upgrade schema once during app boot."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 10000")
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()
    return db_path

def db_health(db_path=DEFAULT_DB):
    try:
        with connect(db_path) as con:
            row = con.execute("PRAGMA quick_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok"), str(row[0] if row else "unknown")
    except Exception as e:
        return False, str(e)

def upsert_draws(df: pd.DataFrame, db_path=DEFAULT_DB, source="upload"):
    required = ["회차","추첨일","번호1","번호2","번호3","번호4","번호5","번호6","보너스"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 열 누락: {missing}")

    count = 0
    with connect(db_path) as con:
        for _, r in df.iterrows():
            nums = [int(r[f"번호{i}"]) for i in range(1,7)]
            bonus = int(r["보너스"])
            if len(set(nums)) != 6:
                raise ValueError(f"{int(r['회차'])}회: 당첨번호 6개가 서로 달라야 합니다.")
            if any(n < 1 or n > 45 for n in nums) or not (1 <= bonus <= 45):
                raise ValueError(f"{int(r['회차'])}회: 번호는 1~45 범위여야 합니다.")
            if bonus in nums:
                raise ValueError(f"{int(r['회차'])}회: 보너스 번호가 본번호와 겹칩니다.")
            nums = sorted(nums)
            vals = (
                int(r["회차"]),
                None if pd.isna(r["추첨일"]) else pd.to_datetime(r["추첨일"]).date().isoformat(),
                *nums, bonus, source,
            )
            con.execute("""
                INSERT INTO draws(draw_no,draw_date,n1,n2,n3,n4,n5,n6,bonus,source)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(draw_no) DO UPDATE SET
                  draw_date=excluded.draw_date,
                  n1=excluded.n1,n2=excluded.n2,n3=excluded.n3,
                  n4=excluded.n4,n5=excluded.n5,n6=excluded.n6,
                  bonus=excluded.bonus,source=excluded.source
            """, vals)
            count += 1
    return count

def upsert_latest(latest: dict, db_path=DEFAULT_DB, draw_date=None, source="official"):
    row = pd.DataFrame([{
        "회차": int(latest["회차"]),
        "추첨일": draw_date if draw_date is not None else latest.get("추첨일", pd.NaT),
        **{f"번호{i}": int(latest[f"번호{i}"]) for i in range(1,7)},
        "보너스": int(latest["보너스"]),
    }])
    return upsert_draws(row, db_path, source=source)

def load_draws(db_path=DEFAULT_DB):
    with connect(db_path) as con:
        df = pd.read_sql_query("""
            SELECT draw_no AS 회차, draw_date AS 추첨일,
                   n1 AS 번호1,n2 AS 번호2,n3 AS 번호3,
                   n4 AS 번호4,n5 AS 번호5,n6 AS 번호6,
                   bonus AS 보너스
            FROM draws ORDER BY draw_no
        """, con)
    if not df.empty:
        df["추첨일"] = pd.to_datetime(df["추첨일"], errors="coerce")
    return df

def latest_draw_no(db_path=DEFAULT_DB):
    with connect(db_path) as con:
        row = con.execute("SELECT MAX(draw_no) FROM draws").fetchone()
    return row[0] if row and row[0] is not None else None

def save_recommendations(picks: pd.DataFrame, target_draw: int, strategy: str,
                         db_path=DEFAULT_DB, birth_mode=False,
                         include_numbers=None, exclude_numbers=None):
    if picks is None or picks.empty:
        return []
    ids = []
    with connect(db_path) as con:
        for _, r in picks.iterrows():
            cur = con.execute("""
                INSERT INTO recommendations(
                  target_draw,strategy,numbers,score,birth_mode,include_numbers,exclude_numbers
                ) VALUES(?,?,?,?,?,?,?)
            """, (
                int(target_draw), strategy, str(r["추천번호"]), float(r.get("점수",0)),
                1 if birth_mode else 0,
                ",".join(map(str, include_numbers or [])),
                ",".join(map(str, exclude_numbers or []))
            ))
            ids.append(cur.lastrowid)
    return ids

def load_recommendations(db_path=DEFAULT_DB, limit=500):
    with connect(db_path) as con:
        return pd.read_sql_query("""
            SELECT id,target_draw AS 대상회차,strategy AS 전략,numbers AS 추천번호,
                   score AS 점수,birth_mode AS 개인화,created_at AS 생성시각
            FROM recommendations ORDER BY id DESC LIMIT ?
        """, con, params=(int(limit),))

def _rank(main_hits, bonus_hit):
    if main_hits == 6: return 1
    if main_hits == 5 and bonus_hit: return 2
    if main_hits == 5: return 3
    if main_hits == 4: return 4
    if main_hits == 3: return 5
    return None

def check_matches(db_path=DEFAULT_DB):
    with connect(db_path) as con:
        rows = con.execute("""
            SELECT r.id,r.target_draw,r.numbers,
                   d.n1,d.n2,d.n3,d.n4,d.n5,d.n6,d.bonus
            FROM recommendations r
            JOIN draws d ON d.draw_no=r.target_draw
        """).fetchall()
        checked = 0
        for row in rows:
            rec_id, draw_no, numbers, *vals = row
            actual = set(map(int, vals[:6]))
            bonus = int(vals[6])
            picked = {int(x.strip()) for x in numbers.replace("·",",").split(",") if x.strip()}
            hits = len(picked & actual)
            bhit = 1 if bonus in picked else 0
            con.execute("""
                INSERT INTO match_results(recommendation_id,target_draw,main_hits,bonus_hit,prize_rank)
                VALUES(?,?,?,?,?)
                ON CONFLICT(recommendation_id) DO UPDATE SET
                  target_draw=excluded.target_draw,
                  main_hits=excluded.main_hits,
                  bonus_hit=excluded.bonus_hit,
                  prize_rank=excluded.prize_rank,
                  checked_at=CURRENT_TIMESTAMP
            """, (rec_id, draw_no, hits, bhit, _rank(hits,bhit)))
            checked += 1
    return checked

def performance_by_strategy(db_path=DEFAULT_DB):
    with connect(db_path) as con:
        return pd.read_sql_query("""
            SELECT r.strategy AS "전략",
                   COUNT(*) AS "검증게임수",
                   ROUND(AVG(m.main_hits),3) AS "평균일치",
                   MAX(m.main_hits) AS "최고일치",
                   SUM(CASE WHEN m.main_hits>=3 THEN 1 ELSE 0 END) AS "3개이상",
                   SUM(CASE WHEN m.prize_rank IS NOT NULL THEN 1 ELSE 0 END) AS "당첨게임수"
            FROM recommendations r
            JOIN match_results m ON m.recommendation_id=r.id
            GROUP BY r.strategy
            ORDER BY "평균일치" DESC, "최고일치" DESC
        """, con)

def match_history(db_path=DEFAULT_DB, limit=500):
    with connect(db_path) as con:
        return pd.read_sql_query("""
            SELECT r.id,r.target_draw AS 대상회차,r.strategy AS 전략,
                   r.numbers AS 추천번호,r.score AS 점수,
                   m.main_hits AS 본번호일치,m.bonus_hit AS 보너스일치,
                   m.prize_rank AS 등수,r.created_at AS 생성시각
            FROM recommendations r
            JOIN match_results m ON m.recommendation_id=r.id
            ORDER BY r.target_draw DESC,r.id DESC LIMIT ?
        """, con, params=(int(limit),))

def clear_draws(db_path=DEFAULT_DB):
    with connect(db_path) as con:
        con.execute("DELETE FROM match_results")
        con.execute("DELETE FROM recommendations")
        con.execute("DELETE FROM draws")
