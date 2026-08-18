
from __future__ import annotations
import pandas as pd
from collections import Counter
from itertools import combinations

REQUIRED_COLS = ["회차","추첨일","번호1","번호2","번호3","번호4","번호5","번호6","보너스"]

ALIASES = {
    "회차": ["회차","draw","draw_no","drwNo"],
    "추첨일": ["추첨일","date","draw_date"],
    "번호1": ["번호1","n1","num1","drwtNo1"],
    "번호2": ["번호2","n2","num2","drwtNo2"],
    "번호3": ["번호3","n3","num3","drwtNo3"],
    "번호4": ["번호4","n4","num4","drwtNo4"],
    "번호5": ["번호5","n5","num5","drwtNo5"],
    "번호6": ["번호6","n6","num6","drwtNo6"],
    "보너스": ["보너스","bonus","bnusNo"],
}

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    lower = {str(c).strip().lower(): c for c in df.columns}
    for target, aliases in ALIASES.items():
        for a in aliases:
            key = a.lower()
            if key in lower:
                rename[lower[key]] = target
                break
    out = df.rename(columns=rename).copy()
    missing = [c for c in REQUIRED_COLS if c not in out.columns]
    if missing:
        raise ValueError(f"필수 열이 없습니다: {missing}")
    out = out[REQUIRED_COLS]
    out["회차"] = pd.to_numeric(out["회차"], errors="coerce").astype("Int64")
    out["추첨일"] = pd.to_datetime(out["추첨일"], errors="coerce")
    for c in REQUIRED_COLS[2:]:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
    out = out.dropna().sort_values("회차").reset_index(drop=True)
    return out

def load_file(path_or_buffer) -> pd.DataFrame:
    name = getattr(path_or_buffer, "name", str(path_or_buffer)).lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(path_or_buffer)
    else:
        try:
            df = pd.read_csv(path_or_buffer, encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(path_or_buffer, encoding="cp949")
    return standardize_columns(df)

def _window(df: pd.DataFrame, n: int | None):
    return df if n is None else df.tail(min(n, len(df)))

def frequency_table(df: pd.DataFrame, windows=(None,100,50,30,10)) -> pd.DataFrame:
    result = pd.DataFrame({"번호": range(1,46)})
    for w in windows:
        part = _window(df, w)
        cnt = Counter()
        for c in [f"번호{i}" for i in range(1,7)]:
            cnt.update(part[c].astype(int).tolist())
        label = "전체" if w is None else f"최근{w}회"
        result[label] = result["번호"].map(cnt).fillna(0).astype(int)
    return result

def absence_table(df: pd.DataFrame) -> pd.DataFrame:
    latest = int(df["회차"].max())
    rows = []
    for n in range(1,46):
        mask = pd.Series(False, index=df.index)
        for c in [f"번호{i}" for i in range(1,7)]:
            mask |= df[c].eq(n)
        if mask.any():
            last = int(df.loc[mask, "회차"].max())
            gap = latest - last
        else:
            last = None
            gap = latest
        rows.append((n,last,gap))
    return pd.DataFrame(rows, columns=["번호","마지막출현회차","미출현회차"])

def draw_pattern_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        nums = sorted(int(r[f"번호{i}"]) for i in range(1,7))
        odd = sum(n % 2 for n in nums)
        low = sum(n <= 22 for n in nums)
        consecutive_pairs = sum(1 for a,b in zip(nums, nums[1:]) if b-a == 1)
        ranges = [
            sum(1 <= n <= 10 for n in nums),
            sum(11 <= n <= 20 for n in nums),
            sum(21 <= n <= 30 for n in nums),
            sum(31 <= n <= 40 for n in nums),
            sum(41 <= n <= 45 for n in nums),
        ]
        gaps = [b-a for a,b in zip(nums, nums[1:])]
        rows.append({
            "회차": int(r["회차"]),
            "합계": sum(nums),
            "홀수개수": odd,
            "짝수개수": 6-odd,
            "저번호(1~22)": low,
            "고번호(23~45)": 6-low,
            "연속번호쌍": consecutive_pairs,
            "최소간격": min(gaps),
            "최대간격": max(gaps),
            "평균간격": round(sum(gaps)/len(gaps),2),
            "1~10": ranges[0], "11~20": ranges[1], "21~30": ranges[2],
            "31~40": ranges[3], "41~45": ranges[4],
        })
    return pd.DataFrame(rows)

def pair_frequency(df: pd.DataFrame, top_n=30) -> pd.DataFrame:
    cnt = Counter()
    for _, r in df.iterrows():
        nums = sorted(int(r[f"번호{i}"]) for i in range(1,7))
        cnt.update(combinations(nums,2))
    rows = [(a,b,c) for (a,b),c in cnt.most_common(top_n)]
    return pd.DataFrame(rows, columns=["번호A","번호B","동반출현횟수"])

def summary(df: pd.DataFrame) -> dict:
    patt = draw_pattern_table(df)
    return {
        "총회차": int(len(df)),
        "최신회차": int(df["회차"].max()),
        "최초회차": int(df["회차"].min()),
        "평균합계": round(float(patt["합계"].mean()),2),
        "중앙합계": round(float(patt["합계"].median()),2),
        "홀짝3대3비율": round(float((patt["홀수개수"] == 3).mean()*100),2),
        "연속번호포함비율": round(float((patt["연속번호쌍"] > 0).mean()*100),2),
    }

def validate(df: pd.DataFrame) -> list[str]:
    issues = []
    if df["회차"].duplicated().any():
        issues.append("중복 회차가 있습니다.")
    for c in [f"번호{i}" for i in range(1,7)] + ["보너스"]:
        bad = ~df[c].between(1,45)
        if bad.any():
            issues.append(f"{c}에 1~45 범위 밖 숫자가 있습니다.")
    for idx, r in df.iterrows():
        nums = [int(r[f"번호{i}"]) for i in range(1,7)]
        if len(set(nums)) != 6:
            issues.append(f"{int(r['회차'])}회: 본번호 6개 중 중복이 있습니다.")
    return issues
