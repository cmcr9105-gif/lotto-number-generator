
from __future__ import annotations
import re
import requests
from bs4 import BeautifulSoup

OFFICIAL_RESULT_URL = "https://www.dhlottery.co.kr/lt645/result"

def fetch_latest_official(timeout=10):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LottoAnalyzer/1.0)"}
    r = requests.get(OFFICIAL_RESULT_URL, headers=headers, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    plain = " ".join(soup.stripped_strings)

    m = re.search(r'(\d{3,4})회', plain)
    if not m:
        raise RuntimeError("공식 페이지에서 최신 회차를 찾지 못했습니다.")
    draw_no = int(m.group(1))

    pos = plain.find("당첨번호")
    segment = plain[pos:pos+900] if pos >= 0 else plain[:1400]
    nums = [int(x) for x in re.findall(r'(?<!\d)([1-9]|[1-3]\d|4[0-5])(?!\d)', segment)]
    uniq = []
    for n in nums:
        if n not in uniq:
            uniq.append(n)
    if len(uniq) < 7:
        raise RuntimeError("당첨번호 6개+보너스를 안정적으로 추출하지 못했습니다.")

    main = sorted(uniq[:6])
    return {
        "회차": draw_no,
        "번호1": main[0], "번호2": main[1], "번호3": main[2],
        "번호4": main[3], "번호5": main[4], "번호6": main[5],
        "보너스": uniq[6],
        "출처": OFFICIAL_RESULT_URL,
    }
