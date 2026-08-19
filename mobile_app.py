
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

from analytics import load_file, frequency_table, absence_table, pair_frequency
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
    initial_sidebar_state="collapsed",
)

# 일반 사용 화면에서 Streamlit 개발자 요소를 최대한 숨기고 모바일 가독성을 높임
st.markdown("""
<style>
header[data-testid="stHeader"] {display:none !important;}
[data-testid="stToolbar"] {display:none !important;}
[data-testid="stDecoration"] {display:none !important;}
#MainMenu {visibility:hidden !important;}
footer {visibility:hidden !important;}
[data-testid="stStatusWidget"] {visibility:hidden !important;}

.block-container {
    padding-top: .65rem;
    padding-bottom: 4.5rem;
    padding-left: .65rem;
    padding-right: .65rem;
    max-width: 760px;
}
h1 {font-size:1.72rem !important; margin:0 0 .15rem 0;}
h2 {font-size:1.35rem !important;}
h3 {font-size:1.13rem !important;}
div[data-testid="stMetric"] {
    border:1px solid rgba(128,128,128,.22);
    border-radius:15px;
    padding:8px;
}
.stButton > button {
    min-height:52px;
    border-radius:14px;
    font-weight:800;
    width:100%;
}
.lotto-card {
    border:1px solid rgba(128,128,128,.24);
    border-radius:17px;
    padding:14px 10px;
    margin:10px 0;
}
.ball {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:40px;height:40px;
    border-radius:50%;
    margin:3px 2px;
    border:2px solid currentColor;
    font-size:15px;font-weight:850;
}
.smallnote {font-size:.80rem;opacity:.72;margin-top:6px;}
.home-note {
    border:1px solid rgba(128,128,128,.20);
    border-radius:14px;
    padding:11px 13px;
    margin:.35rem 0 .8rem 0;
}
@media (max-width:600px) {
    .ball {width:37px;height:37px;font-size:14px;}
}
</style>
""", unsafe_allow_html=True)

st.title("🎯 로또당첨번호 생성기")
st.caption("차단대응 안정화 버전")
st.markdown(
    '<div class="home-note">① 데이터 갱신 → ② 번호 생성 → ③ 저장·당첨 확인 순서로 사용하세요.</div>',
    unsafe_allow_html=True
)

# DB 확인
df = load_draws(DB_PATH)

# 최초 화면: 복잡한 메뉴 없이 자동 구축 버튼을 가장 먼저 노출
if df.empty:
    st.subheader("처음 한 번만 설정")
    st.write("자동조회가 차단될 수 있어 **기존 당첨번호 파일 업로드가 가장 안정적**입니다.")

    if st.button("📚 최근 200회 자동 준비 시도", type="primary", use_container_width=True):
        prog = st.progress(0)
        msg = st.empty()
        try:
            def _progress(done, total, draw_no):
                prog.progress(min(1.0, done / total))
                msg.caption(f"{draw_no}회 확인 중 · {done}/{total}")

            rows = fetch_recent_official(count=200, progress=_progress)
            auto_df = pd.DataFrame(rows)
            if "추첨일" not in auto_df.columns:
                auto_df["추첨일"] = pd.NaT
            auto_df = auto_df[
                ["회차","추첨일","번호1","번호2","번호3","번호4","번호5","번호6","보너스"]
            ]
            n = upsert_draws(auto_df, DB_PATH, source="official-auto")
            prog.progress(1.0)
            msg.success(f"{n}개 회차 준비 완료")
            st.rerun()
        except Exception as e:
            prog.empty()
            msg.empty()
            st.error("자동 데이터 준비에 실패했습니다.")
            with st.expander("수동 파일 업로드"):
                st.caption("동행복권에서 받은 CSV/XLSX 파일을 올려주세요.")
                uploaded = st.file_uploader(
                    "당첨번호 파일 선택",
                    type=["csv","xlsx","xls"],
                    key="first_upload",
                    label_visibility="collapsed"
                )
                if uploaded is not None:
                    try:
                        udf = load_file(uploaded)
                        if st.button("파일 저장", use_container_width=True):
                            n = upsert_draws(udf, DB_PATH, source="upload")
                            st.success(f"{n}개 회차 저장 완료")
                            st.rerun()
                    except Exception:
                        st.error("파일 형식을 확인해주세요.")
    st.markdown("---")
    st.caption("파일이 없으면 우선 최근 회차를 직접 입력해 앱을 시작할 수도 있습니다.")
    with st.expander("✍️ 당첨결과 1회 직접 입력"):
        first_draw = st.number_input("회차", min_value=1, value=1, step=1, key="first_draw")
        cols = st.columns(3)
        first_nums = []
        defaults = [1,2,3,4,5,6]
        for i in range(6):
            first_nums.append(
                cols[i % 3].number_input(
                    f"번호 {i+1}", 1, 45, defaults[i], key=f"first_n{i+1}"
                )
            )
        first_bonus = st.number_input("보너스", 1, 45, 7, key="first_bonus")
        if st.button("첫 데이터 저장", use_container_width=True):
            nums = list(map(int, first_nums))
            if len(set(nums)) != 6 or int(first_bonus) in nums:
                st.error("번호 중복을 확인해주세요.")
            else:
                row = pd.DataFrame([{
                    "회차": int(first_draw), "추첨일": pd.NaT,
                    **{f"번호{i+1}": nums[i] for i in range(6)},
                    "보너스": int(first_bonus)
                }])
                upsert_draws(row, DB_PATH, source="manual")
                st.success("저장했습니다.")
                st.rerun()
    st.stop()

latest_draw = int(df["회차"].max())

# 상단 상태
c1, c2, c3 = st.columns(3)
c1.metric("최신 회차", f"{latest_draw}회")
c2.metric("보유 데이터", f"{len(df)}회")
c3.metric("저장 번호", len(load_recommendations(DB_PATH, 99999)))

# 가장 많이 쓰는 기능은 첫 화면에
st.subheader("이번 주 사용")

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 최신 결과 자동확인", use_container_width=True):
        try:
            latest = fetch_latest_official()
            upsert_latest(latest, DB_PATH)
            check_matches(DB_PATH)
            st.success(f"{latest['회차']}회 결과를 저장했습니다.")
            st.rerun()
        except Exception:
            st.warning("자동확인이 차단되었습니다. 아래 '직접 입력'을 사용하면 됩니다.")

with c2:
    st.info(f"다음 대상: 제{latest_draw + 1}회")

with st.expander("✍️ 최신 당첨결과 직접 입력", expanded=False):
    st.caption("자동조회가 막혀도 회차와 숫자 7개만 입력하면 즉시 DB에 저장됩니다.")
    수동회차 = st.number_input(
        "회차",
        min_value=1,
        value=latest_draw + 1,
        step=1,
        key="manual_draw_no"
    )
    수동날짜 = st.date_input("추첨일", value=date.today(), key="manual_draw_date")

    st.write("당첨번호 6개")
    a1,a2,a3 = st.columns(3)
    a4,a5,a6 = st.columns(3)
    n1 = a1.number_input("번호 1", 1, 45, 1, key="mn1")
    n2 = a2.number_input("번호 2", 1, 45, 2, key="mn2")
    n3 = a3.number_input("번호 3", 1, 45, 3, key="mn3")
    n4 = a4.number_input("번호 4", 1, 45, 4, key="mn4")
    n5 = a5.number_input("번호 5", 1, 45, 5, key="mn5")
    n6 = a6.number_input("번호 6", 1, 45, 6, key="mn6")
    bonus = st.number_input("보너스 번호", 1, 45, 7, key="mnb")

    if st.button("✅ 입력한 당첨결과 저장", use_container_width=True):
        nums = [int(n1),int(n2),int(n3),int(n4),int(n5),int(n6)]
        if len(set(nums)) != 6:
            st.error("당첨번호 6개는 서로 달라야 합니다.")
        elif int(bonus) in nums:
            st.error("보너스 번호는 당첨번호 6개와 달라야 합니다.")
        else:
            row = pd.DataFrame([{
                "회차": int(수동회차),
                "추첨일": pd.to_datetime(수동날짜),
                "번호1": nums[0], "번호2": nums[1], "번호3": nums[2],
                "번호4": nums[3], "번호5": nums[4], "번호6": nums[5],
                "보너스": int(bonus)
            }])
            upsert_draws(row, DB_PATH, source="manual")
            matched = check_matches(DB_PATH)
            st.success(f"{int(수동회차)}회 저장 완료 · 저장번호 {matched}건 당첨대조")
            st.rerun()

탭_생성, 탭_분석, 탭_결과, 탭_성과, 탭_설정 = st.tabs(
    ["🎲 번호 생성", "📊 번호 분석", "🏆 당첨 확인", "📈 성과", "⚙️ 설정"]
)

with 탭_생성:
    st.subheader(f"제{latest_draw + 1}회 추천번호")

    생성방식 = st.selectbox(
        "생성 방식",
        ["혼합형", "균형형", "빈도형", "미출현형", "완전랜덤"],
        index=0
    )

    c1, c2 = st.columns(2)
    게임수 = c1.selectbox("게임 수", [5, 10, 15, 20], index=0)
    후보수 = c2.selectbox("분석 후보 수", [2000, 5000, 10000, 20000], index=2)

    포함번호, 제외번호, 최대중복 = [], [], 3
    개인화사용, 개인화가중치 = False, None

    with st.expander("상세 설정"):
        포함번호 = st.multiselect("반드시 포함할 번호", list(range(1, 46)))
        제외번호 = st.multiselect("제외할 번호", [n for n in range(1, 46) if n not in 포함번호])
        최대중복 = st.slider("게임 사이 최대 중복 번호", 1, 5, 3)
        개인화사용 = st.toggle("생년월일 개인화 사용(재미용)")

        if 개인화사용:
            생년월일 = st.text_input("생년월일", placeholder="예: 음력 1967-12-19")
            if 생년월일:
                개인화가중치 = birth_based_weights(생년월일)
                st.caption(
                    "개인화 선호수: " +
                    " · ".join(map(str, favorite_numbers_from_birth(생년월일)))
                )

    if st.button("🎯 이번 주 번호 만들기", type="primary", use_container_width=True):
        try:
            후보, _ = generate_candidates(
                df, 생성방식, 후보수, seed=None,
                include=포함번호,
                exclude=제외번호,
                personal_weights=개인화가중치,
            )
            추천 = select_diverse_top(후보, 게임수, 최대중복)
            st.session_state["추천번호"] = 추천
            st.session_state["추천정보"] = {
                "target_draw": latest_draw + 1,
                "strategy": 생성방식,
                "birth_mode": 개인화사용,
                "include": 포함번호,
                "exclude": 제외번호,
            }
        except Exception as e:
            st.error(f"번호 생성 중 오류가 발생했습니다: {e}")

    if "추천번호" in st.session_state:
        추천 = st.session_state["추천번호"]

        for _, 행 in 추천.iterrows():
            번호들 = [x.strip() for x in str(행["추천번호"]).split("·")]
            공 = "".join(f'<span class="ball">{n}</span>' for n in 번호들)
            st.markdown(
                f'<div class="lotto-card"><b>{int(행["게임"])}게임</b><br>{공}'
                f'<div class="smallnote">분석점수 {float(행["점수"]):.1f} · 번호합 {int(행["합계"])}</div></div>',
                unsafe_allow_html=True,
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 추천번호 저장", use_container_width=True):
                정보 = st.session_state["추천정보"]
                ids = save_recommendations(
                    추천,
                    정보["target_draw"],
                    정보["strategy"],
                    DB_PATH,
                    birth_mode=정보["birth_mode"],
                    include_numbers=정보["include"],
                    exclude_numbers=정보["exclude"],
                )
                st.success(f"{len(ids)}게임 저장했습니다.")
        with c2:
            st.download_button(
                "📥 번호표 저장",
                추천.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                "로또추천번호.csv",
                "text/csv",
                use_container_width=True,
            )

with 탭_분석:
    st.subheader("번호 통계")
    기간 = st.selectbox(
        "분석 기간",
        ["최근10회", "최근30회", "최근50회", "최근100회", "전체"],
        index=2,
    )
    빈도 = frequency_table(df)
    상위 = 빈도[["번호", 기간]].sort_values(기간, ascending=False).head(15)
    st.caption("출현 빈도 상위")
    st.bar_chart(상위.set_index("번호"))

    st.caption("오랫동안 나오지 않은 번호")
    st.dataframe(
        absence_table(df).sort_values("미출현회차", ascending=False).head(15),
        hide_index=True,
        use_container_width=True,
    )

    st.caption("함께 자주 나온 번호")
    st.dataframe(
        pair_frequency(df, 15),
        hide_index=True,
        use_container_width=True,
    )

with 탭_결과:
    st.subheader("저장번호 당첨 확인")
    if st.button("🔍 당첨 결과 확인", use_container_width=True):
        n = check_matches(DB_PATH)
        st.success(f"{n}건을 확인했습니다.")

    기록 = match_history(DB_PATH, 100)
    if 기록.empty:
        st.info("아직 확인할 저장번호가 없습니다.")
    else:
        st.dataframe(기록, hide_index=True, use_container_width=True)

with 탭_성과:
    st.subheader("생성 방식별 누적 성과")
    성과 = performance_by_strategy(DB_PATH)
    if 성과.empty:
        st.info("추천번호와 실제 결과가 쌓이면 자동으로 표시됩니다.")
    else:
        st.dataframe(성과, hide_index=True, use_container_width=True)
        st.bar_chart(성과.set_index("전략")["평균일치"])
    st.caption("과거 결과는 미래 당첨을 보장하지 않습니다.")

with 탭_설정:
    st.subheader("데이터 설정")

    if st.button("📚 최근 200회 다시 자동 준비", use_container_width=True):
        prog = st.progress(0)
        msg = st.empty()
        try:
            def _progress2(done, total, draw_no):
                prog.progress(min(1.0, done / total))
                msg.caption(f"{draw_no}회 확인 중 · {done}/{total}")
            rows = fetch_recent_official(count=200, progress=_progress2)
            auto_df = pd.DataFrame(rows)
            if "추첨일" not in auto_df.columns:
                auto_df["추첨일"] = pd.NaT
            auto_df = auto_df[
                ["회차","추첨일","번호1","번호2","번호3","번호4","번호5","번호6","보너스"]
            ]
            n = upsert_draws(auto_df, DB_PATH, source="official-auto")
            check_matches(DB_PATH)
            msg.success(f"{n}개 회차 저장/갱신 완료")
            st.rerun()
        except Exception:
            prog.empty()
            msg.empty()
            st.warning("자동 준비에 실패했습니다.")

    with st.expander("수동으로 당첨번호 파일 올리기"):
        uploaded = st.file_uploader(
            "CSV/XLSX 파일 선택",
            type=["csv", "xlsx", "xls"],
            key="manual_upload",
        )
        if uploaded is not None:
            try:
                udf = load_file(uploaded)
                if st.button("업로드 파일 저장", use_container_width=True):
                    n = upsert_draws(udf, DB_PATH, source="upload")
                    st.success(f"{n}개 회차 저장/갱신 완료")
                    st.rerun()
            except Exception:
                st.error("파일 형식을 확인해주세요.")

    st.markdown("---")
    st.caption("통계점수·생년월일 개인화는 실제 당첨확률을 의미하지 않습니다.")
