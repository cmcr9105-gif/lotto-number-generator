from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from analytics import load_file, frequency_table, absence_table, pair_frequency
from generator import safe_generate_games
from updater import fetch_latest_official
from personalizer import birth_based_weights, favorite_numbers_from_birth
from db import (
    init_db, db_health, upsert_draws, upsert_latest, load_draws,
    save_recommendations, load_recommendations, check_matches,
    performance_by_strategy, match_history,
)

DB_PATH = "lotto_app.db"

st.set_page_config(
    page_title="로또당첨번호 생성기",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🎯 로또당첨번호 생성기")
st.caption("9단계 복구판 v4 · 세션상태/강제 rerun 제거")

# -------------------------
# DB boot: no session_state, no rerun
# -------------------------
try:
    init_db(DB_PATH)
    db_ok, db_msg = db_health(DB_PATH)
except Exception as exc:
    db_ok, db_msg = False, f"{type(exc).__name__}: {exc}"

if not db_ok:
    st.error("DB 초기화에 실패했습니다.")
    st.code(db_msg)
    st.stop()

try:
    df = load_draws(DB_PATH)
except Exception as exc:
    st.error("당첨번호 DB를 읽지 못했습니다.")
    st.code(f"{type(exc).__name__}: {exc}")
    st.stop()

latest_draw = int(df["회차"].max()) if not df.empty else 0

c1, c2, c3 = st.columns(3)
c1.metric("최신 회차", f"{latest_draw}회" if latest_draw else "없음")
c2.metric("보유 데이터", f"{len(df)}회")
try:
    recent_recs = load_recommendations(DB_PATH, 500)
    rec_count = len(recent_recs)
except Exception:
    recent_recs = pd.DataFrame()
    rec_count = 0
c3.metric("최근 저장번호", rec_count)

st.markdown("### 1. 당첨결과 데이터")

with st.expander("🔄 자동조회(보조 기능)", expanded=False):
    if st.button("최신 회차 자동확인", use_container_width=True):
        try:
            latest = fetch_latest_official()
            upsert_latest(latest, DB_PATH)
            matched = check_matches(DB_PATH)
            st.success(f"{latest['회차']}회 저장 완료 · {matched}건 당첨대조")
            st.info("화면 상단 회차 표시는 다음 조작 또는 새로고침 때 갱신됩니다.")
        except Exception as exc:
            st.warning(f"자동조회 실패: {type(exc).__name__}: {exc}")

with st.expander("✍️ 최신 당첨결과 직접 입력", expanded=df.empty):
    default_draw = latest_draw + 1 if latest_draw else 1
    draw_no = st.number_input("회차", min_value=1, value=default_draw, step=1)
    draw_date = st.date_input("추첨일", value=date.today())
    nums = [
        st.number_input(f"번호 {i}", min_value=1, max_value=45, value=i, key=f"manual_n{i}")
        for i in range(1, 7)
    ]
    bonus = st.number_input("보너스 번호", min_value=1, max_value=45, value=7)

    if st.button("✅ 당첨결과 저장", type="primary", use_container_width=True):
        try:
            clean = sorted(int(x) for x in nums)
            b = int(bonus)
            if len(set(clean)) != 6:
                raise ValueError("당첨번호 6개는 서로 달라야 합니다.")
            if b in clean:
                raise ValueError("보너스 번호는 당첨번호와 달라야 합니다.")
            row = pd.DataFrame([{
                "회차": int(draw_no), "추첨일": pd.to_datetime(draw_date),
                **{f"번호{i+1}": clean[i] for i in range(6)}, "보너스": b,
            }])
            upsert_draws(row, DB_PATH, source="manual")
            matched = check_matches(DB_PATH)
            st.success(f"{int(draw_no)}회 저장 완료 · {matched}건 당첨대조")
            st.info("강제 재실행을 하지 않도록 변경했습니다. 상단 수치는 다음 조작 때 갱신됩니다.")
        except Exception as exc:
            st.error(f"저장 오류: {type(exc).__name__}: {exc}")

with st.expander("📁 과거 당첨번호 파일 업로드", expanded=False):
    uploaded = st.file_uploader("CSV/XLSX 파일 선택", type=["csv", "xlsx", "xls"])
    if uploaded is not None:
        try:
            udf = load_file(uploaded)
            st.write(f"읽은 회차: {len(udf)}개")
            if st.button("업로드 자료 저장", use_container_width=True):
                n = upsert_draws(udf, DB_PATH, source="upload")
                matched = check_matches(DB_PATH)
                st.success(f"{n}개 회차 저장/갱신 완료 · {matched}건 당첨대조")
        except Exception as exc:
            st.error(f"파일 처리 오류: {type(exc).__name__}: {exc}")

if df.empty:
    st.info("당첨번호 데이터가 없습니다. 최신 회차를 직접 입력하거나 과거 파일을 업로드하세요.")
    st.stop()

if len(df) < 10:
    st.warning(f"현재 {len(df)}회 데이터만 있습니다. 기능은 작동하지만 통계 의미는 제한적입니다.")

st.markdown("### 2. 번호 생성")
section = st.selectbox(
    "기능 선택",
    ["🎲 번호 생성", "📊 번호 분석", "🏆 당첨 확인", "📈 성과"],
)

if section == "🎲 번호 생성":
    strategy = st.selectbox("생성 방식", ["혼합형", "균형형", "빈도형", "미출현형", "완전랜덤"])
    games = st.selectbox("게임 수", [5, 10, 15, 20], index=0)
    include, exclude, max_overlap = [], [], 3
    personal_on, personal_weights = False, None

    with st.expander("상세 설정", expanded=False):
        include = st.multiselect("반드시 포함할 번호", list(range(1, 46)))
        exclude = st.multiselect("제외할 번호", [n for n in range(1, 46) if n not in include])
        max_overlap = st.slider("게임 사이 최대 중복 번호", 1, 5, 3)
        personal_on = st.toggle("생년월일 개인화(재미용)")
        if personal_on:
            birth_text = st.text_input("생년월일", placeholder="예: 음력 1967-12-19")
            if birth_text:
                personal_weights = birth_based_weights(birth_text)
                st.caption("개인화 선호수: " + " · ".join(map(str, favorite_numbers_from_birth(birth_text))))

    if st.button("🎯 이번 회차 번호 추출", type="primary", use_container_width=True):
        try:
            # No session_state, no file logging, no st.rerun.
            records = safe_generate_games(
                df,
                strategy=strategy,
                n_games=int(games),
                seed=None,
                include=include,
                exclude=exclude,
                personal_weights=personal_weights,
                max_overlap=int(max_overlap),
                sample_size=160,
            )
            if not records:
                raise ValueError("추천번호를 만들지 못했습니다.")

            picks = pd.DataFrame(records)
            ids = save_recommendations(
                picks,
                target_draw=int(latest_draw + 1),
                strategy=str(strategy),
                db_path=DB_PATH,
                birth_mode=bool(personal_on),
                include_numbers=[int(x) for x in include],
                exclude_numbers=[int(x) for x in exclude],
            )

            st.success(f"{len(ids)}게임 추출·자동저장 완료")
            for row in records:
                st.write(f"**{int(row['게임'])}게임**  |  {row['추천번호']}  |  점수 {float(row['점수']):.1f}  |  합계 {int(row['합계'])}")
        except Exception as exc:
            st.error(f"번호 생성 오류: {type(exc).__name__}: {exc}")

    st.markdown("#### 최근 저장 추천번호")
    try:
        latest_saved = load_recommendations(DB_PATH, 20)
        if latest_saved.empty:
            st.caption("아직 저장된 추천번호가 없습니다.")
        else:
            st.dataframe(latest_saved, hide_index=True, use_container_width=True)
    except Exception as exc:
        st.warning(f"저장 추천번호 조회 오류: {type(exc).__name__}: {exc}")

elif section == "📊 번호 분석":
    try:
        period = st.selectbox("분석 기간", ["최근10회", "최근30회", "최근50회", "최근100회", "전체"])
        freq = frequency_table(df)
        st.bar_chart(freq.set_index("번호")[period])
        st.dataframe(absence_table(df).sort_values("미출현회차", ascending=False).head(15), hide_index=True, use_container_width=True)
        st.dataframe(pair_frequency(df, 15), hide_index=True, use_container_width=True)
    except Exception as exc:
        st.error(f"번호 분석 오류: {type(exc).__name__}: {exc}")

elif section == "🏆 당첨 확인":
    if st.button("🔍 저장번호 당첨대조", use_container_width=True):
        try:
            st.success(f"{check_matches(DB_PATH)}건 확인 완료")
        except Exception as exc:
            st.error(f"당첨대조 오류: {type(exc).__name__}: {exc}")
    try:
        hist = match_history(DB_PATH, 100)
        if hist.empty:
            st.info("대조 가능한 저장번호가 없습니다.")
        else:
            st.dataframe(hist, hide_index=True, use_container_width=True)
    except Exception as exc:
        st.error(f"당첨 기록 오류: {type(exc).__name__}: {exc}")

else:
    try:
        perf = performance_by_strategy(DB_PATH)
        if perf.empty:
            st.info("추천번호와 실제 결과가 쌓이면 표시됩니다.")
        else:
            st.dataframe(perf, hide_index=True, use_container_width=True)
    except Exception as exc:
        st.error(f"성과 조회 오류: {type(exc).__name__}: {exc}")

st.markdown("---")
st.caption("※ 통계점수·생년월일 개인화는 실제 당첨확률을 의미하지 않습니다.")
