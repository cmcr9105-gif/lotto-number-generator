
# 로또당첨번호 생성기 — 4단계 지속사용형 MVP

## 4단계 추가 기능
- SQLite 로컬 DB 영구 저장
- 당첨번호 CSV/XLSX 누적/갱신
- 동행복권 공식 최신 회차 확인·저장 시도
- 추천번호 + 대상회차 저장
- 실제 당첨번호 자동 대조
- 1~5등 판정
- 전략별 누적 성과판
- SQLite DB 백업
- 매주 업데이트 스크립트
- Windows 원클릭 실행

## 실행
Windows: `run_windows.bat` 더블클릭

직접 실행:
```bash
pip install -r requirements.txt
streamlit run app.py
```

매주 업데이트:
```bash
python weekly_update.py
```

## 자동수집 안전장치
공식 사이트 구조 변경으로 자동 확인이 실패할 수 있습니다.
그 경우 동행복권 공식 통계에서 받은 CSV/XLSX를 업로드하면 DB는 계속 누적됩니다.

## 주의
통계점수·사주 개인화·백테스트는 실제 당첨확률을 뜻하지 않습니다.
