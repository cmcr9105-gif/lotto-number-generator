
from analytics import load_file, frequency_table, absence_table, pair_frequency, summary, validate
import sys

if len(sys.argv) < 2:
    print("사용법: python analyze.py lotto_history.csv")
    raise SystemExit(1)

df = load_file(sys.argv[1])
print("요약:", summary(df))
issues = validate(df)
print("검증:", "정상" if not issues else issues)
print("\n최근/전체 빈도 상위 10")
print(frequency_table(df).sort_values("전체", ascending=False).head(10).to_string(index=False))
print("\n장기 미출현 상위 10")
print(absence_table(df).sort_values("미출현회차", ascending=False).head(10).to_string(index=False))
print("\n동반출현 상위 10")
print(pair_frequency(df, 10).to_string(index=False))
