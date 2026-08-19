
from __future__ import annotations

import json
import re
import time
from datetime import datetime, date, time as dtime, timedelta, timezone
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
DRAW1_DATE = date(2002, 12, 7)

OFFICIAL_ENDPOINTS = [
    # 동행복권 신형 결과 조회 경로 후보
    "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do?srchDir=center&srchLtEpsd={draw_no}",
    # 구형/호환 경로
    "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={draw_no}",
    "https://www.dhlottery.co.kr/gameResult.do?method=byWin&drwNo={draw_no}",
    "https://m.dhlottery.co.kr/gameResult.do?method=byWin&drwNo={draw_no}",
    "https://www.dhlottery.co.kr/lt645/result?drawNo={draw_no}",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

def estimated_latest_draw(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(KST)
    today = now.date()
    if today < DRAW1_DATE:
        return 0
    days_since_sat = (today.weekday() - 5) % 7
    most_recent_sat = today - timedelta(days=days_since_sat)
    if today.weekday() == 5 and now.time() < dtime(20, 35):
        most_recent_sat -= timedelta(days=7)
    return max(0, (most_recent_sat - DRAW1_DATE).days // 7 + 1)

def _validate(draw: dict) -> dict:
    need = ["회차"] + [f"번호{i}" for i in range(1, 7)] + ["보너스"]
    for k in need:
        if k not in draw:
            raise ValueError(f"필수값 누락: {k}")
    draw_no = int(draw["회차"])
    main = [int(draw[f"번호{i}"]) for i in range(1, 7)]
    bonus = int(draw["보너스"])
    if draw_no < 1:
        raise ValueError("회차 오류")
    if len(set(main)) != 6 or any(n < 1 or n > 45 for n in main):
        raise ValueError("본번호 검증 실패")
    if bonus < 1 or bonus > 45 or bonus in main:
        raise ValueError("보너스 검증 실패")
    main = sorted(main)
    out = {"회차": draw_no}
    for i, n in enumerate(main, 1):
        out[f"번호{i}"] = n
    out["보너스"] = bonus
    if draw.get("추첨일"):
        out["추첨일"] = str(draw["추첨일"])
    return out


def _walk_dicts(obj):
    """중첩 JSON 안의 dict를 모두 순회합니다."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dicts(v)

def _parse_new_json_shape(payload, requested_draw: int) -> Optional[dict]:
    """신형 동행복권 응답의 여러 키 형태를 유연하게 해석합니다."""
    for d in _walk_dicts(payload):
        draw_no = (
            d.get("ltEpsd") or d.get("epsd") or d.get("drawNo") or
            d.get("drwNo") or d.get("round")
        )
        if draw_no is None:
            continue
        try:
            if int(draw_no) != int(requested_draw):
                continue
        except Exception:
            continue

        # 리스트 형태
        list_candidates = [
            d.get("winNum"), d.get("winNums"), d.get("lottoNum"),
            d.get("lottoNums"), d.get("winningNumbers"), d.get("numbers")
        ]
        main = None
        for cand in list_candidates:
            if isinstance(cand, list) and len(cand) >= 6:
                try:
                    nums = [int(x) for x in cand[:6]]
                    if len(set(nums)) == 6 and all(1 <= n <= 45 for n in nums):
                        main = nums
                        break
                except Exception:
                    pass

        # 개별 키 형태
        if main is None:
            key_sets = [
                [f"lottoNo{i}" for i in range(1,7)],
                [f"drwtNo{i}" for i in range(1,7)],
                [f"winNo{i}" for i in range(1,7)],
                [f"rankNo{i}" for i in range(1,7)],
            ]
            for keys in key_sets:
                if all(k in d for k in keys):
                    try:
                        nums = [int(d[k]) for k in keys]
                        if len(set(nums)) == 6 and all(1 <= n <= 45 for n in nums):
                            main = nums
                            break
                    except Exception:
                        pass

        if main is None:
            continue

        bonus = (
            d.get("bonusNo") or d.get("bnusNo") or d.get("bonus") or
            d.get("bonusNum") or d.get("bnsNo")
        )
        if bonus is None:
            continue

        draw = {"회차": int(requested_draw), "보너스": int(bonus)}
        for i, n in enumerate(main, 1):
            draw[f"번호{i}"] = n
        draw_date = d.get("ltRflYmd") or d.get("drawDate") or d.get("drwNoDate")
        if draw_date:
            draw["추첨일"] = str(draw_date)
        try:
            return _validate(draw)
        except Exception:
            continue
    return None

def _parse_json_payload(payload, requested_draw: int) -> Optional[dict]:
    newer = _parse_new_json_shape(payload, requested_draw)
    if newer:
        return newer
    if not isinstance(payload, dict):
        return None
    draw_no = payload.get("drwNo") or payload.get("drawNo") or payload.get("round")
    if draw_no is None:
        return None
    try:
        draw_no = int(draw_no)
    except Exception:
        return None
    if draw_no != int(requested_draw):
        return None

    main = []
    for i in range(1, 7):
        v = payload.get(f"drwtNo{i}") or payload.get(f"lottoNo{i}") or payload.get(f"no{i}")
        if v is None:
            return None
        main.append(int(v))
    bonus = payload.get("bnusNo") or payload.get("bonusNo") or payload.get("bonus")
    if bonus is None:
        return None

    draw = {"회차": draw_no, "보너스": int(bonus)}
    for i, n in enumerate(main, 1):
        draw[f"번호{i}"] = n
    dt = payload.get("drwNoDate") or payload.get("drawDate")
    if dt:
        draw["추첨일"] = dt
    return _validate(draw)

def _parse_html(html: str, requested_draw: int) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = "\n".join(s.get_text(" ", strip=True) for s in soup.find_all("script"))

    found_draw = None
    for pat in [r'"drwNo"\s*:\s*"?(\d+)"?', r'"drawNo"\s*:\s*"?(\d+)"?']:
        m = re.search(pat, scripts)
        if m:
            found_draw = int(m.group(1))
            break

    main = []
    for i in range(1, 7):
        m = re.search(rf'"(?:drwtNo{i}|lottoNo{i}|no{i})"\s*:\s*"?(\d{{1,2}})"?', scripts)
        if not m:
            main = []
            break
        main.append(int(m.group(1)))
    mb = re.search(r'"(?:bnusNo|bonusNo|bonus)"\s*:\s*"?(\d{1,2})"?', scripts)
    if main and mb and (found_draw in (None, requested_draw)):
        draw = {"회차": requested_draw, "보너스": int(mb.group(1))}
        for i, n in enumerate(main, 1):
            draw[f"번호{i}"] = n
        try:
            return _validate(draw)
        except Exception:
            pass

    candidates = []
    selectors = [
        '[class*="ball"]',
        '[class*="lotto"] [class*="num"]',
        '[class*="win"] [class*="num"]',
        '[aria-label*="당첨"]',
    ]
    for sel in selectors:
        for el in soup.select(sel):
            txt = el.get_text(" ", strip=True)
            candidates.extend(
                int(x)
                for x in re.findall(r'(?<!\d)([1-9]|[1-3]\d|4[0-5])(?!\d)', txt)
            )

    uniq = []
    for n in candidates:
        if n not in uniq:
            uniq.append(n)
    if len(uniq) >= 7:
        draw = {"회차": requested_draw, "보너스": uniq[6]}
        for i, n in enumerate(uniq[:6], 1):
            draw[f"번호{i}"] = n
        try:
            return _validate(draw)
        except Exception:
            pass

    plain = " ".join(soup.stripped_strings)
    for anchor in ["당첨번호", "당첨 번호"]:
        pos = plain.find(anchor)
        if pos < 0:
            continue
        segment = plain[max(0, pos - 80):pos + 1200]
        nums = [
            int(x)
            for x in re.findall(r'(?<!\d)([1-9]|[1-3]\d|4[0-5])(?!\d)', segment)
        ]
        for start in range(max(1, len(nums) - 6)):
            block = nums[start:start + 7]
            if len(block) < 7:
                continue
            if len(set(block[:6])) == 6 and block[6] not in block[:6]:
                draw = {"회차": requested_draw, "보너스": block[6]}
                for i, n in enumerate(block[:6], 1):
                    draw[f"번호{i}"] = n
                try:
                    return _validate(draw)
                except Exception:
                    continue
    return None

def fetch_draw(draw_no: int, timeout: int = 12, session: Optional[requests.Session] = None) -> dict:
    draw_no = int(draw_no)
    sess = session or requests.Session()

    for template in OFFICIAL_ENDPOINTS:
        url = template.format(draw_no=draw_no)
        try:
            r = sess.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code != 200:
                continue
            ctype = (r.headers.get("content-type") or "").lower()

            if "json" in ctype or r.text.lstrip().startswith("{"):
                try:
                    payload = r.json()
                except Exception:
                    try:
                        payload = json.loads(r.text)
                    except Exception:
                        payload = None
                parsed = _parse_json_payload(payload, draw_no) if payload else None
                if parsed:
                    parsed["출처"] = url
                    return parsed

            parsed = _parse_html(r.text, draw_no)
            if parsed:
                parsed["출처"] = url
                return parsed
        except Exception:
            continue

    raise RuntimeError(
        f"{draw_no}회 공식 데이터 자동조회 실패. "
        "동행복권 페이지 구조 또는 접근정책이 변경되었을 수 있습니다."
    )

def fetch_latest_official(timeout: int = 12) -> dict:
    guess = estimated_latest_draw()
    sess = requests.Session()
    last_error = None
    for draw_no in range(guess, max(0, guess - 4), -1):
        try:
            return fetch_draw(draw_no, timeout=timeout, session=sess)
        except Exception as e:
            last_error = e
    raise RuntimeError(f"공식 최신 회차 자동조회 실패: {last_error}")

def fetch_recent_official(
    count: int = 200,
    timeout: int = 10,
    progress: Optional[Callable[[int, int, int], None]] = None,
    pause: float = 0.05,
) -> list[dict]:
    latest = fetch_latest_official(timeout=timeout)
    latest_no = int(latest["회차"])
    start = max(1, latest_no - int(count) + 1)

    sess = requests.Session()
    rows = []
    total = latest_no - start + 1

    for idx, draw_no in enumerate(range(start, latest_no + 1), 1):
        try:
            row = latest if draw_no == latest_no else fetch_draw(draw_no, timeout=timeout, session=sess)
            rows.append(row)
        except Exception:
            pass
        if progress:
            progress(idx, total, draw_no)
        if pause:
            time.sleep(pause)

    if not rows:
        raise RuntimeError("최근 회차 자동구축에 실패했습니다.")
    return rows
