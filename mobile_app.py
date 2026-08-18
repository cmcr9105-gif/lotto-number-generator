
import streamlit as st
import pandas as pd
from pathlib import Path

from analytics import load_file, frequency_table, absence_table, pair_frequency, summary
from generator import generate_candidates, select_diverse_top
from updater import fetch_latest_official, fetch_recent_official
from personalizer import birth_based_weights, favorite_numbers_from_birth
from db import (
    init_db, upsert_draws, upsert_latest, load_draws,
    save_recommendations, load_recommendations, check_matches,
    performance_by_strategy, match_history
)

DB_PATH = "lotto_app.db"
init_db(DB_PATH)

st.set_page_config(
    page_title="로또당첨번호 생성기",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container {
    padding-top: .7rem;
    padding-bottom: 5rem;
    max-width: 760px;
}
h1 {font-size:1.8rem !important; margin-bottom:.15rem;}
div[data-testid="stMetric"] {
    border:1px solid rgba(128,128,128,.25);
    border-radius:14px;
    padding:8px;
}
.stButton > button {
    min-height:52px;
    border-radius:14px;
    font-weight:800;
    width:100%;
}
.lotto-card {
    border:1px solid rgba(128,128,128,.25);
    border-radius:16px;
    padding:14px 10px;
    margin:9px 0;
}
.ball {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:42px;height:42px;
    border-radius:50%;
    margin:3px;
    border:2px solid currentColor;
    font-size:16px;font-weight:800;
}
.smallnote {font-size:.82rem;opacity:.75;margin-top:6px;}
@media (max-width:600px) {
    .block-container {padding-left:.55rem;padding-right:.55rem;}
    .ball {width:38px;height:38px;font-size:15px;margin:2px;}
}
</style>
""", unsafe_allow_html=True)

st.title("🎯 로또당첨번호 생성기")
st.caption("6단계 · 자동업데이트 모바일 버전")
st.info("통계점수·사주 개인화는 실제 당첨확률이 아닙니다.")

with st.expander("⚙️ 데이터 관리", expanded=False):
    uploaded = st.file_uploader("과거 당첨번호 CSV/XLSX", type=["csv","xlsx","xls"])
    if uploaded is not None:
        try:
            udf = load_file(uploaded)
            if st.button("업로드 자료를 DB에 저장", key="save_upload"):
                n = upsert_draws(udf, DB_PATH, source="upload")
                st.success(f"{n}개 회차 저장/갱신")
                st.rerun()
        except Exception as e:
            st.error(f"파일 오류: {e}")

    c_up1, c_up2 = st.columns(2)
    with c_up1:
        if st.button("🔄 최신 1회 자동저장", key="official_update", use_container_width=True):
            try:
                latest = fetch_latest_official()
                upsert_latest(latest, DB_PATH)
                check_matches(DB_PATH)
                st.success(f"{latest['회차']}회 저장 완료")
                st.rerun()
            except Exception as e:
                st.error(f"최신회차 자동조회 실패: {e}")

    with c_up2:
        if st.button("📚 최근 200회 자동구축", key="bootstrap_200", use_container_width=True):
            prog = st.progress(0)
            status = st.empty()
            try:
                def _progress(done, total, draw_no):
                    prog.progress(min(1.0, done / total))
                    status.caption(f"{draw_no}회 확인 중 · {done}/{total}")
                rows = fetch_recent_official(count=200, progress=_progress)
                auto_df = pd.DataFrame(rows)
                if "추첨일" not in auto_df.columns:
                    auto_df["추첨일"] = pd.NaT
                auto_df = auto_df[["회차","추첨일","번호1","번호2","번호3","번호4","번호5","번호6","보너스"]]
                n = upsert_draws(auto_df, DB_PATH, source="official-auto")
                check_matches(DB_PATH)
                prog.progress(1.0)
                status.success(f"공식 데이터 {n}개 회차 저장/갱신 완료")
                st.rerun()
            except Exception as e:
                prog.empty()
                status.empty()
                st.error(f"자동구축 실패: {e}")
                st.caption("이 경우 공식 CSV/XLSX 업로드 방식은 계속 사용할 수 있습니다.")

    st.caption("자동조회는 날짜로 완료 회차를 계산한 뒤 여러 공식 주소를 순차 검증합니다.")

df = load_draws(DB_PATH)
if df.empty:
    st.warning("DB가 비어 있습니다. 위 '데이터 관리'에서 **최근 200회 자동구축**을 먼저 눌러보세요.")
    st.caption("자동구축이 막히면 CSV/XLSX 업로드를 사용하면 됩니다.")
    st.stop()

latest_draw = int(df["회차"].max())

c1,c2,c3 = st.columns(3)
c1.metric("최신", f"{latest_draw}회")
c2.metric("DB", f"{len(df)}회")
c3.metric("저장", len(load_recommendations(DB_PATH, 99999)))

tab_gen, tab_stats, tab_result, tab_perf = st.tabs(["🎲 생성","📊 분석","🏆 결과","📈 성과"])

with tab_gen:
    st.subheader(f"제{latest_draw+1}회 추천번호")

    strategy = st.selectbox("생성 방식", ["혼합형","균형형","빈도형","미출현형","완전랜덤"])
    c1,c2 = st.columns(2)
    games = c1.selectbox("게임 수", [5,10,15,20], index=0)
    candidates_n = c2.selectbox("분석 후보", [2000,5000,10000,20000], index=2)

    include, exclude, max_overlap = [], [], 3
    personal_on, personal_weights = False, None

    with st.expander("고급 설정", expanded=False):
        include = st.multiselect("반드시 포함", list(range(1,46)))
        exclude = st.multiselect("제외 번호", [n for n in range(1,46) if n not in include])
        max_overlap = st.slider("게임 간 최대 중복", 1, 5, 3)
        personal_on = st.toggle("사주·생년월일 개인화(재미용)")
        if personal_on:
            birth_text = st.text_input("생년월일", placeholder="예: 음력 1967-12-19")
            if birth_text:
                personal_weights = birth_based_weights(birth_text)
                st.caption("개인화 선호수: " + " · ".join(map(str, favorite_numbers_from_birth(birth_text))))

    if st.button("🎯 이번 주 번호 생성", type="primary", use_container_width=True):
        try:
            cand, _ = generate_candidates(
                df, strategy, candidates_n, seed=None,
                include=include, exclude=exclude,
                personal_weights=personal_weights
            )
            picks = select_diverse_top(cand, games, max_overlap)
            st.session_state["mobile_picks"] = picks
            st.session_state["mobile_meta"] = {
                "target_draw": latest_draw + 1,
                "strategy": strategy,
                "birth_mode": personal_on,
                "include": include,
                "exclude": exclude
            }
        except Exception as e:
            st.error(str(e))

    if "mobile_picks" in st.session_state:
        picks = st.session_state["mobile_picks"]
        for _, row in picks.iterrows():
            nums = [x.strip() for x in str(row["추천번호"]).split("·")]
            balls = "".join(f'<span class="ball">{n}</span>' for n in nums)
            st.markdown(
                f'<div class="lotto-card"><b>{int(row["게임"])}게임</b><br>{balls}'
                f'<div class="smallnote">통계점수 {float(row["점수"]):.1f} · 합계 {int(row["합계"])}</div></div>',
                unsafe_allow_html=True
            )

        c1,c2 = st.columns(2)
        with c1:
            if st.button("💾 저장", use_container_width=True):
                m = st.session_state["mobile_meta"]
                ids = save_recommendations(
                    picks, m["target_draw"], m["strategy"], DB_PATH,
                    birth_mode=m["birth_mode"],
                    include_numbers=m["include"], exclude_numbers=m["exclude"]
                )
                st.success(f"{len(ids)}게임 저장")
        with c2:
            st.download_button(
                "📥 CSV",
                picks.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                "lotto_mobile_recommendations.csv",
                "text/csv", use_container_width=True
            )

with tab_stats:
    st.subheader("번호 분석")
    period = st.selectbox("분석 기간", ["최근10회","최근30회","최근50회","최근100회","전체"], index=2)
    freq = frequency_table(df)
    top = freq[["번호",period]].sort_values(period, ascending=False).head(15)
    st.bar_chart(top.set_index("번호"))

    st.caption("장기 미출현 상위")
    st.dataframe(
        absence_table(df).sort_values("미출현회차", ascending=False).head(15),
        hide_index=True, use_container_width=True
    )

    st.caption("동반출현 상위")
    st.dataframe(pair_frequency(df, 15), hide_index=True, use_container_width=True)

with tab_result:
    st.subheader("저장번호 당첨 대조")
    if st.button("🔍 지금 대조", use_container_width=True):
        st.success(f"{check_matches(DB_PATH)}건 확인")
    hist = match_history(DB_PATH, 100)
    if hist.empty:
        st.info("아직 대조 가능한 저장번호가 없습니다.")
    else:
        st.dataframe(hist, hide_index=True, use_container_width=True)

with tab_perf:
    st.subheader("전략별 누적 성과")
    perf = performance_by_strategy(DB_PATH)
    if perf.empty:
        st.info("저장번호와 실제 결과가 쌓이면 표시됩니다.")
    else:
        st.dataframe(perf, hide_index=True, use_container_width=True)
        st.bar_chart(perf.set_index("전략")["평균일치"])
    st.caption("과거 성과는 미래 결과를 보장하지 않습니다.")
