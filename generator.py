
from __future__ import annotations
import math
import random
import pandas as pd
from collections import Counter
from itertools import combinations
from analytics import frequency_table, absence_table, draw_pattern_table

NUMBERS = list(range(1, 46))

def _minmax(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series([0.5]*len(s), index=s.index)
    return (s-lo)/(hi-lo)

def build_number_scores(df: pd.DataFrame, strategy: str="혼합형") -> pd.DataFrame:
    freq = frequency_table(df)
    absn = absence_table(df)
    score = freq.merge(absn, on="번호", how="left")

    for c in ["전체","최근100회","최근50회","최근30회","최근10회","미출현회차"]:
        score[c+"_N"] = _minmax(score[c])

    # 전략별 가중치
    weights = {
        "균형형": {"전체_N":0.15,"최근100회_N":0.10,"최근50회_N":0.10,"최근30회_N":0.05,"최근10회_N":0.05,"미출현회차_N":0.10},
        "빈도형": {"전체_N":0.30,"최근100회_N":0.20,"최근50회_N":0.20,"최근30회_N":0.10,"최근10회_N":0.10,"미출현회차_N":0.00},
        "미출현형": {"전체_N":0.10,"최근100회_N":0.05,"최근50회_N":0.05,"최근30회_N":0.05,"최근10회_N":0.00,"미출현회차_N":0.55},
        "혼합형": {"전체_N":0.20,"최근100회_N":0.15,"최근50회_N":0.15,"최근30회_N":0.10,"최근10회_N":0.05,"미출현회차_N":0.20},
        "완전랜덤": {"전체_N":0.0,"최근100회_N":0.0,"최근50회_N":0.0,"최근30회_N":0.0,"최근10회_N":0.0,"미출현회차_N":0.0},
    }
    w = weights.get(strategy, weights["혼합형"])
    score["번호점수"] = sum(score[k]*v for k,v in w.items())
    if strategy == "완전랜덤":
        score["번호점수"] = 1.0
    return score[["번호","번호점수","전체","최근100회","최근50회","최근30회","최근10회","미출현회차"]]

def _pattern_reference(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"sum_low": 100.0, "sum_high": 180.0, "odd_mode": 3, "low_mode": 3, "consecutive_rate": 0.5}
    patt = draw_pattern_table(df)
    if patt.empty:
        return {"sum_low": 100.0, "sum_high": 180.0, "odd_mode": 3, "low_mode": 3, "consecutive_rate": 0.5}
    sums = patt["합계"]
    q1, q3 = sums.quantile([0.15,0.85])
    return {
        "sum_low": float(q1),
        "sum_high": float(q3),
        "odd_mode": int(patt["홀수개수"].mode().iloc[0]),
        "low_mode": int(patt["저번호(1~22)"].mode().iloc[0]),
        "consecutive_rate": float((patt["연속번호쌍"]>0).mean()),
    }

def combination_features(nums):
    nums = sorted(nums)
    odd = sum(n%2 for n in nums)
    low = sum(n<=22 for n in nums)
    total = sum(nums)
    consec = sum(1 for a,b in zip(nums, nums[1:]) if b-a==1)
    ranges = [
        sum(1<=n<=10 for n in nums),
        sum(11<=n<=20 for n in nums),
        sum(21<=n<=30 for n in nums),
        sum(31<=n<=40 for n in nums),
        sum(41<=n<=45 for n in nums),
    ]
    last_digits = [n%10 for n in nums]
    same_last_max = max(Counter(last_digits).values())
    gaps = [b-a for a,b in zip(nums, nums[1:])]
    return {
        "합계": total,
        "홀수개수": odd,
        "저번호개수": low,
        "연속번호쌍": consec,
        "최대구간집중": max(ranges),
        "동일끝수최대": same_last_max,
        "평균간격": sum(gaps)/5,
        "최소간격": min(gaps),
        "최대간격": max(gaps),
    }

def score_combination(nums, number_score_map, ref, strategy="혼합형", rng=None):
    feats = combination_features(nums)

    # 번호 자체 점수
    ns = sum(number_score_map[n] for n in nums)/6

    # 균형 점수
    odd_score = 1 - abs(feats["홀수개수"]-3)/3
    low_score = 1 - abs(feats["저번호개수"]-3)/3

    if ref["sum_low"] <= feats["합계"] <= ref["sum_high"]:
        sum_score = 1.0
    else:
        dist = min(abs(feats["합계"]-ref["sum_low"]), abs(feats["합계"]-ref["sum_high"]))
        sum_score = max(0.0, 1 - dist/80)

    range_score = 1.0 if feats["최대구간집중"] <= 2 else (0.55 if feats["최대구간집중"] == 3 else 0.15)
    last_score = 1.0 if feats["동일끝수최대"] <= 2 else (0.5 if feats["동일끝수최대"] == 3 else 0.1)
    gap_score = 1.0 if 4 <= feats["평균간격"] <= 9 else 0.5

    # 연속수는 완전 배제하지 않음
    if feats["연속번호쌍"] == 0:
        consec_score = 0.85
    elif feats["연속번호쌍"] == 1:
        consec_score = 1.0
    else:
        consec_score = 0.55

    if strategy == "완전랜덤":
        total = (rng or random).random()
    else:
        total = (
            ns*0.35 +
            odd_score*0.12 +
            low_score*0.12 +
            sum_score*0.14 +
            range_score*0.10 +
            last_score*0.06 +
            gap_score*0.05 +
            consec_score*0.06
        )
    return round(total*100, 2), feats

def generate_candidates(df: pd.DataFrame, strategy="혼합형", n_candidates=10000, seed=None, include=None, exclude=None, personal_weights=None):
    rng = random.Random(seed)
    include = sorted(set(int(x) for x in (include or [])))
    exclude = sorted(set(int(x) for x in (exclude or [])))
    if set(include) & set(exclude):
        raise ValueError("포함 번호와 제외 번호가 겹칩니다.")
    if len(include) > 6:
        raise ValueError("포함 번호는 최대 6개입니다.")
    if any(n < 1 or n > 45 for n in include + exclude):
        raise ValueError("번호는 1~45 범위여야 합니다.")
    if len(set(NUMBERS)-set(exclude)) < 6:
        raise ValueError("제외 번호가 너무 많습니다.")

    scores = build_number_scores(df, strategy)
    score_map = dict(zip(scores["번호"], scores["번호점수"]))
    ref = _pattern_reference(df)

    # 번호선택 가중치: 완전랜덤 외에는 점수+바닥값
    if strategy == "완전랜덤":
        weights = [1.0]*45
    else:
        weights = [max(0.05, score_map[n]+0.10) for n in NUMBERS]
    if personal_weights:
        weights = [w * float(personal_weights.get(n, 1.0)) for n, w in zip(NUMBERS, weights)]

    seen = set()
    rows = []
    attempts = 0
    max_attempts = max(n_candidates*8, 5000)

    while len(rows) < n_candidates and attempts < max_attempts:
        attempts += 1
        # random.choices는 중복이 생기므로 가중치 기반 비복원 추출 직접 구현
        pool = [n for n in NUMBERS if n not in exclude and n not in include]
        w = [weights[n-1] for n in pool]
        picked = include.copy()
        for _ in range(6-len(include)):
            totalw = sum(w)
            r = rng.random()*totalw
            acc = 0.0
            idx = 0
            for i, ww in enumerate(w):
                acc += ww
                if acc >= r:
                    idx = i
                    break
            picked.append(pool.pop(idx))
            w.pop(idx)
        nums = tuple(sorted(picked))
        if nums in seen:
            continue
        seen.add(nums)
        sc, feats = score_combination(nums, score_map, ref, strategy, rng=rng)
        rows.append({
            "번호1":nums[0],"번호2":nums[1],"번호3":nums[2],
            "번호4":nums[3],"번호5":nums[4],"번호6":nums[5],
            "점수":sc, **feats
        })

    if not rows:
        return pd.DataFrame(columns=[
            "번호1","번호2","번호3","번호4","번호5","번호6","점수","합계",
            "홀수개수","저번호개수","연속번호쌍","최대구간집중","동일끝수최대",
            "평균간격","최소간격","최대간격"
        ]), scores
    out = pd.DataFrame(rows).sort_values("점수", ascending=False).reset_index(drop=True)
    return out, scores

def select_diverse_top(candidates: pd.DataFrame, n_games=5, max_overlap=3):
    selected = []
    for _, r in candidates.iterrows():
        nums = {int(r[f"번호{i}"]) for i in range(1,7)}
        ok = True
        for s in selected:
            if len(nums & s["nums"]) > max_overlap:
                ok = False
                break
        if ok:
            selected.append({"row":r, "nums":nums})
            if len(selected) >= n_games:
                break

    # 너무 엄격해서 부족하면 남은 상위권으로 채움
    if len(selected) < n_games:
        selected_keys = {tuple(sorted(x["nums"])) for x in selected}
        for _, r in candidates.iterrows():
            nums = {int(r[f"번호{i}"]) for i in range(1,7)}
            key = tuple(sorted(nums))
            if key not in selected_keys:
                selected.append({"row":r, "nums":nums})
                selected_keys.add(key)
                if len(selected) >= n_games:
                    break

    rows = []
    for idx, item in enumerate(selected, 1):
        r = item["row"]
        rows.append({
            "게임": idx,
            "추천번호": " · ".join(str(int(r[f"번호{i}"])) for i in range(1,7)),
            "점수": float(r["점수"]),
            "합계": int(r["합계"]),
            "홀수": int(r["홀수개수"]),
            "저번호": int(r["저번호개수"]),
            "연속쌍": int(r["연속번호쌍"]),
        })
    return pd.DataFrame(rows)

def simple_backtest(df: pd.DataFrame, strategy="혼합형", test_draws=20, candidates_per_draw=2000, seed=42):
    """
    각 테스트 회차 직전 데이터만 사용해 추천 5게임을 만들고,
    실제 당첨번호와 최대 몇 개 맞았는지 측정.
    """
    if len(df) < test_draws + 30:
        return pd.DataFrame()

    results = []
    df = df.sort_values("회차").reset_index(drop=True)
    start = len(df) - test_draws

    for idx in range(start, len(df)):
        train = df.iloc[:idx].copy()
        actual_row = df.iloc[idx]
        actual = {int(actual_row[f"번호{i}"]) for i in range(1,7)}

        cand, _ = generate_candidates(train, strategy, n_candidates=candidates_per_draw, seed=seed+idx)
        picks = select_diverse_top(cand, n_games=5, max_overlap=3)

        max_hit = 0
        hit_counts = []
        for _, p in picks.iterrows():
            nums = {int(x.strip()) for x in p["추천번호"].split("·")}
            hit = len(nums & actual)
            hit_counts.append(hit)
            max_hit = max(max_hit, hit)

        results.append({
            "회차": int(actual_row["회차"]),
            "최대일치개수": max_hit,
            "5게임일치개수": ",".join(map(str, hit_counts))
        })

    return pd.DataFrame(results)

# -----------------------------------------------------------------------------
# STEP9 v3: 초경량 안전 생성기
# pandas 기반 대형 후보 DataFrame을 만들지 않고 번호 45개의 통계만 계산한 뒤
# 소규모 후보를 순수 Python 자료구조로 생성한다.
# -----------------------------------------------------------------------------
def safe_generate_games(df: pd.DataFrame, strategy="혼합형", n_games=5, seed=None,
                        include=None, exclude=None, personal_weights=None,
                        max_overlap=3, sample_size=320):
    rng = random.Random(seed)
    include = sorted(set(int(x) for x in (include or [])))
    exclude = sorted(set(int(x) for x in (exclude or [])))
    if set(include) & set(exclude):
        raise ValueError("포함 번호와 제외 번호가 겹칩니다.")
    if len(include) > 6:
        raise ValueError("포함 번호는 최대 6개입니다.")
    allowed = [n for n in NUMBERS if n not in exclude]
    if len(allowed) < 6:
        raise ValueError("제외 번호가 너무 많습니다.")

    # 번호별 출현 횟수와 마지막 출현 간격을 한 번의 순회로 계산
    counts_all = {n: 0 for n in NUMBERS}
    counts_recent = {n: 0 for n in NUMBERS}
    last_seen = {n: None for n in NUMBERS}
    rows = [] if df is None else list(df.sort_values("회차").itertuples(index=False))
    total_rows = len(rows)
    recent_start = max(0, total_rows - 50)

    for idx, row in enumerate(rows):
        vals = []
        for i in range(1, 7):
            try:
                vals.append(int(getattr(row, f"번호{i}")))
            except Exception:
                # itertuples에서 한글 열명이 변환될 수 있으므로 iloc 경로는 아래에서 보완
                vals = []
                break
        if not vals and df is not None:
            rr = df.iloc[idx]
            vals = [int(rr[f"번호{i}"]) for i in range(1, 7)]
        for n in vals:
            counts_all[n] += 1
            if idx >= recent_start:
                counts_recent[n] += 1
            last_seen[n] = idx

    max_all = max(counts_all.values()) if total_rows else 1
    max_recent = max(counts_recent.values()) if total_rows else 1
    absences = {
        n: (total_rows if last_seen[n] is None else total_rows - 1 - last_seen[n])
        for n in NUMBERS
    }
    max_abs = max(absences.values()) if absences else 1

    base = {}
    for n in NUMBERS:
        fa = counts_all[n] / max(1, max_all)
        fr = counts_recent[n] / max(1, max_recent)
        ab = absences[n] / max(1, max_abs)
        if strategy == "완전랜덤":
            s = 1.0
        elif strategy == "빈도형":
            s = 0.60 * fa + 0.40 * fr
        elif strategy == "미출현형":
            s = 0.25 * fa + 0.15 * fr + 0.60 * ab
        elif strategy == "균형형":
            s = 0.34 * fa + 0.33 * fr + 0.33 * ab
        else:  # 혼합형
            s = 0.40 * fa + 0.30 * fr + 0.30 * ab
        if personal_weights:
            s *= float(personal_weights.get(n, 1.0))
        base[n] = max(0.02, float(s))

    def weighted_pick(pool, k):
        pool = list(pool)
        picked = []
        for _ in range(k):
            ws = [base[n] for n in pool]
            total = sum(ws)
            r = rng.random() * total
            acc = 0.0
            chosen_idx = len(pool) - 1
            for j, w in enumerate(ws):
                acc += w
                if acc >= r:
                    chosen_idx = j
                    break
            picked.append(pool.pop(chosen_idx))
        return picked

    def combo_score(nums):
        nums = sorted(nums)
        if strategy == "완전랜덤":
            stat = rng.random()
        else:
            stat = sum(base[n] for n in nums) / 6.0
        odd = sum(n % 2 for n in nums)
        low = sum(n <= 22 for n in nums)
        total = sum(nums)
        consec = sum(1 for a, b in zip(nums, nums[1:]) if b - a == 1)
        balance = max(0.0, 1.0 - abs(odd - 3) * 0.12 - abs(low - 3) * 0.10)
        sum_balance = 1.0 if 100 <= total <= 180 else 0.75
        score = (stat * 0.70 + balance * 0.20 + sum_balance * 0.10) * 100
        return round(score, 2), total, odd, low, consec

    candidates = []
    seen = set()
    pool_base = [n for n in allowed if n not in include]
    target_samples = max(80, min(int(sample_size), 500))
    attempts = 0
    while len(candidates) < target_samples and attempts < target_samples * 12:
        attempts += 1
        if len(pool_base) < (6 - len(include)):
            raise ValueError("포함/제외 번호 조건으로 6개 조합을 만들 수 없습니다.")
        nums = tuple(sorted(include + weighted_pick(pool_base, 6 - len(include))))
        if nums in seen:
            continue
        seen.add(nums)
        sc, total, odd, low, consec = combo_score(nums)
        candidates.append((sc, nums, total, odd, low, consec))

    if not candidates:
        raise ValueError("추천 후보를 만들지 못했습니다.")
    candidates.sort(key=lambda x: x[0], reverse=True)

    selected = []
    for item in candidates:
        nums_set = set(item[1])
        if all(len(nums_set & set(s[1])) <= int(max_overlap) for s in selected):
            selected.append(item)
            if len(selected) >= int(n_games):
                break
    if len(selected) < int(n_games):
        used = {x[1] for x in selected}
        for item in candidates:
            if item[1] not in used:
                selected.append(item)
                used.add(item[1])
                if len(selected) >= int(n_games):
                    break

    records = []
    for idx, (sc, nums, total, odd, low, consec) in enumerate(selected, 1):
        records.append({
            "게임": idx,
            "추천번호": " · ".join(map(str, nums)),
            "점수": float(sc),
            "합계": int(total),
            "홀수": int(odd),
            "저번호": int(low),
            "연속쌍": int(consec),
        })
    return records
