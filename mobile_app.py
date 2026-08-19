
import streamlit as st
import pandas as pd
import gc
from datetime import date
from pathlib import Path

from analytics import load_file, frequency_table, absence_table, pair_frequency
from generator import safe_generate_games
from updater import fetch_latest_official
from personalizer import birth_based_weights, favorite_numbers_from_birth
from db import (
    init_db, db_health, upsert_draws, upsert_latest, load_draws,
    save_recommendations, load_recommendations, check_matches,
    performance_by_strategy, match_history
)

DB_PATH = "lotto_app.db"

st.set_page_config(
    page_title="로또당첨번호 생성기",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
header[data-testid="stHeader"] {display:none !important;}
[data-testid="stToolbar"] {display:none !important;}
#MainMenu {visibility:hidden !important;}
footer {visibility:hidden !important;}
.block-container {
  padding-top:.7rem; padding-bottom:4rem; padding-left:.7rem; padding-right:.7rem;
  max-width:760px;
}
h1 {font-size:1.72rem !important; margin-bottom:.15rem;}
.stButton > button {min-height:50px; border-radius:14px; font-weight:800; width:100%;}
div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.20); border-radius:14px; padding:7px;}
.lotto-card {border:1px solid rgba(128,128,128,.24); border-radius:16px; padding:13px 10px; margin:9px 0;}
.ball {
  display:inline-flex; align-items:center; justify-content:center;
  width:38px; height:38px; border-radius:50%; margin:2px;
  border:2px solid currentColor; font-size:14px; font-weight:850;
}
.smallnote {font-size:.80rem; opacity:.72; margin-top:5px;}
</style>
""", unsafe_allow_html=True)

st.title("🎯 로또당첨번호 생성기")
st.caption("9단계 안정화 3차 · 초경량 번호추출 + 진단로그 적용")

# DB 초기화/복구
try:
    init_db(DB_PATH)
    db_ok, db_msg = db_health(DB_PATH)
except Exception as e:
    db_ok, db_msg = False, str(e)

if not db_ok:
    st.error("저장소 점검 중 문제가 발견되었습니다.")
    st.code(db_msg)
    st.info("앱을 한 번 재부팅한 뒤 다시 확인해주세요.")
    st.stop()

# 안전 로드
try:
    df = load_draws(DB_PATH)
except Exception as e:
    st.error("저장된 당첨번호를 읽는 중 오류가 발생했습니다.")
    st.code(str(e))
    st.stop()

def save_manual_draw(draw_no, draw_date, nums, bonus, source="manual"):
    nums = [int(x) for x in nums]
    bonus = int(bonus)
    if len(set(nums)) != 6:
        raise ValueError("당첨번호 6개는 서로 달라야 합니다.")
    if any(n < 1 or n > 45 for n in nums) or not (1 <= bonus <= 45):
        raise ValueError("번호는 1~45 범위여야 합니다.")
    if bonus in nums:
        raise ValueError("보너스 번호는 당첨번호와 달라야 합니다.")
    nums = sorted(nums)
    row = pd.DataFrame([{
        "회차": int(draw_no),
        "추첨일": pd.to_datetime(draw_date) if draw_date else pd.NaT,
        **{f"번호{i+1}": nums[i] for i in range(6)},
        "보너스": bonus,
    }])
    upsert_draws(row, DB_PATH, source=source)
    return check_matches(DB_PATH)

# 저장 완료 메시지를 rerun 이후에도 유지
if st.session_state.pop("save_success", False):
    st.success(st.session_state.pop("save_message", "저장 완료"))

latest_draw = int(df["회차"].max()) if not df.empty else 0

# 상단 상태
c1, c2, c3 = st.columns(3)
c1.metric("최신 회차", f"{latest_draw}회" if latest_draw else "없음")
c2.metric("보유 데이터", f"{len(df)}회")
try:
    rec_count = len(load_recommendations(DB_PATH, 100000))
except Exception:
    rec_count = 0
c3.metric("저장 번호", rec_count)

st.markdown("### 1. 당첨결과 데이터")

# 자동조회는 보조 기능
with st.expander("🔄 자동조회(보조 기능)", expanded=False):
    st.caption("Streamlit 서버에서 동행복권 접속이 차단될 수 있습니다. 실패해도 앱은 계속 사용할 수 있습니다.")
    if st.button("최신 회차 자동확인", use_container_width=True):
        try:
            latest = fetch_latest_official()
            upsert_latest(latest, DB_PATH)
            matched = check_matches(DB_PATH)
            st.session_state["save_success"] = True
            st.session_state["save_message"] = f"{latest['회차']}회 자동 저장 완료 · {matched}건 당첨대조"
            st.rerun()
        except Exception:
            st.warning("자동조회가 차단되었습니다. 아래 직접 입력을 사용해주세요.")

# 직접 입력은 항상 보임
with st.expander("✍️ 최신 당첨결과 직접 입력", expanded=(df.empty)):
    default_draw = latest_draw + 1 if latest_draw else 1
    draw_no = st.number_input("회차", min_value=1, value=default_draw, step=1, key="manual_draw")
    draw_date = st.date_input("추첨일", value=date.today(), key="manual_date")

    st.caption("당첨번호 6개를 순서대로 입력하세요.")
    n1 = st.number_input("번호 1", 1, 45, 1, key="manual_n1")
    n2 = st.number_input("번호 2", 1, 45, 2, key="manual_n2")
    n3 = st.number_input("번호 3", 1, 45, 3, key="manual_n3")
    n4 = st.number_input("번호 4", 1, 45, 4, key="manual_n4")
    n5 = st.number_input("번호 5", 1, 45, 5, key="manual_n5")
    n6 = st.number_input("번호 6", 1, 45, 6, key="manual_n6")
    bonus = st.number_input("보너스 번호", 1, 45, 7, key="manual_bonus")

    if st.button("✅ 당첨결과 저장", type="primary", use_container_width=True):
        try:
            matched = save_manual_draw(
                draw_no, draw_date, [n1,n2,n3,n4,n5,n6], bonus
            )
            st.session_state["save_success"] = True
            st.session_state["save_message"] = f"{int(draw_no)}회 저장 완료 · 저장번호 {matched}건 당첨대조"
            # 입력 위젯 값을 억지로 삭제하지 않고 안전하게 전체 앱 재실행
            st.rerun()
        except Exception as e:
            st.error(str(e))

with st.expander("📁 과거 당첨번호 파일 업로드", expanded=False):
    uploaded = st.file_uploader("CSV/XLSX 파일 선택", type=["csv","xlsx","xls"])
    if uploaded is not None:
        try:
            udf = load_file(uploaded)
            st.write(f"읽은 회차: {len(udf)}개")
            if st.button("업로드 자료 저장", use_container_width=True):
                n = upsert_draws(udf, DB_PATH, source="upload")
                matched = check_matches(DB_PATH)
                st.session_state["save_success"] = True
                st.session_state["save_message"] = f"{n}개 회차 저장/갱신 완료 · 저장번호 {matched}건 당첨대조"
                st.rerun()
        except Exception as e:
            st.error(f"파일을 읽지 못했습니다: {e}")

# 데이터가 없더라도 화면을 없애지 않음
if df.empty:
    st.info("아직 당첨번호 데이터가 없습니다. 위에서 최신 회차 1건을 직접 입력하거나 과거 파일을 업로드하세요.")
    st.markdown("---")
    st.caption("데이터를 저장해도 이 화면은 사라지지 않도록 수정했습니다.")
    st.stop()

# 데이터가 적을 때 명확한 안내
if len(df) < 10:
    st.warning(
        f"현재 데이터가 {len(df)}회뿐입니다. 앱은 작동하지만 통계 분석의 의미가 매우 약합니다. "
        "가능하면 과거 당첨번호 파일을 추가해주세요."
    )

st.markdown("### 2. 번호 생성")

section = st.radio(
    "기능 선택",
    ["🎲 번호 생성", "📊 번호 분석", "🏆 당첨 확인", "📈 성과"],
    horizontal=True,
    label_visibility="collapsed",
    key="main_section",
)

if section == "🎲 번호 생성":
    strategy = st.selectbox("생성 방식", ["혼합형","균형형","빈도형","미출현형","완전랜덤"])
    c1, c2 = st.columns(2)
    games = c1.selectbox("게임 수", [5,10,15,20], index=0)
    # Streamlit Cloud 안정성을 위해 한 번에 만드는 후보 수를 제한한다.
    candidates_n = c2.selectbox("분석 후보 수", [500,1000,1500,2000], index=1)

    include, exclude, max_overlap = [], [], 3
    personal_on, personal_weights = False, None

    with st.expander("상세 설정"):
        include = st.multiselect("반드시 포함할 번호", list(range(1,46)))
        exclude = st.multiselect("제외할 번호", [n for n in range(1,46) if n not in include])
        max_overlap = st.slider("게임 사이 최대 중복 번호", 1, 5, 3)
        personal_on = st.toggle("생년월일 개인화(재미용)")
        if personal_on:
            birth_text = st.text_input("생년월일", placeholder="예: 음력 1967-12-19")
            if birth_text:
                personal_weights = birth_based_weights(birth_text)
                st.caption("개인화 선호수: " + " · ".join(map(str, favorite_numbers_from_birth(birth_text))))

    if st.button("🎯 이번 회차 번호 추출", type="primary", use_container_width=True):
        old_records = st.session_state.get("last_pick_records")
        old_meta = st.session_state.get("last_meta")
        log_path = Path("lotto_generation_diag.log")

        def diag(msg):
            try:
                from datetime import datetime
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().isoformat(timespec='seconds')} | {msg}\n")
            except Exception:
                pass

        try:
            diag("CLICK_START")
            diag(f"DATA_ROWS={len(df)} STRATEGY={strategy} GAMES={games}")
            with st.spinner("이번 회차 추천번호를 계산하고 있습니다..."):
                diag("SAFE_GENERATOR_START")
                records = safe_generate_games(
                    df, strategy=strategy, n_games=int(games), seed=None,
                    include=include, exclude=exclude,
                    personal_weights=personal_weights, max_overlap=int(max_overlap),
                    sample_size=320
                )
                diag(f"SAFE_GENERATOR_DONE RECORDS={len(records)}")
                if not records:
                    raise ValueError("추천번호를 선택하지 못했습니다.")

                st.session_state["last_pick_records"] = records
                st.session_state["last_meta"] = {
                    "target_draw": int(latest_draw + 1),
                    "strategy": str(strategy),
                    "birth_mode": bool(personal_on),
                    "include": [int(x) for x in include],
                    "exclude": [int(x) for x in exclude],
                }
                st.session_state.pop("generation_error", None)
                diag("SESSION_SAVE_DONE")
        except Exception as e:
            diag(f"ERROR={type(e).__name__}: {e}")
            if old_records is not None:
                st.session_state["last_pick_records"] = old_records
            if old_meta is not None:
                st.session_state["last_meta"] = old_meta
            st.session_state["generation_error"] = f"{type(e).__name__}: {e}"

    if st.session_state.get("generation_error"):
        st.error(f"번호 생성 오류: {st.session_state['generation_error']}")

    # 구버전 세션에 DataFrame이 남아 있으면 1회 자동 변환
    if "last_pick_records" not in st.session_state and "last_picks" in st.session_state:
        try:
            legacy = st.session_state.pop("last_picks")
            if isinstance(legacy, pd.DataFrame) and not legacy.empty:
                st.session_state["last_pick_records"] = [
                    {
                        "게임": int(r["게임"]),
                        "추천번호": str(r["추천번호"]),
                        "점수": float(r["점수"]),
                        "합계": int(r["합계"]),
                        "홀수": int(r.get("홀수", 0)),
                        "저번호": int(r.get("저번호", 0)),
                        "연속쌍": int(r.get("연속쌍", 0)),
                    }
                    for _, r in legacy.iterrows()
                ]
        except Exception:
            st.session_state.pop("last_picks", None)

    records = st.session_state.get("last_pick_records", [])
    if records:
        st.success(f"{len(records)}게임 추출 완료")
        for row in records:
            try:
                nums = [x.strip() for x in str(row.get("추천번호", "")).split("·") if x.strip()]
                balls = "".join(f'<span class="ball">{n}</span>' for n in nums)
                st.markdown(
                    f'<div class="lotto-card"><b>{int(row.get("게임", 0))}게임</b><br>{balls}'
                    f'<div class="smallnote">분석점수 {float(row.get("점수", 0)):.1f} · 번호합 {int(row.get("합계", 0))}</div></div>',
                    unsafe_allow_html=True
                )
            except Exception as e:
                st.warning(f"추천번호 표시 중 일부 오류가 발생했습니다: {e}")

        if st.button("💾 추천번호 저장", use_container_width=True):
            try:
                meta = st.session_state.get("last_meta")
                if not meta:
                    raise ValueError("추천번호 생성 정보가 없습니다. 번호를 다시 추출해주세요.")
                picks_for_save = pd.DataFrame(records)
                ids = save_recommendations(
                    picks_for_save, meta["target_draw"], meta["strategy"], DB_PATH,
                    birth_mode=meta["birth_mode"],
                    include_numbers=meta["include"], exclude_numbers=meta["exclude"]
                )
                st.success(f"{len(ids)}게임 저장 완료")
            except Exception as e:
                st.error(f"추천번호 저장 오류: {e}")

elif section == "📊 번호 분석":
    # 중요: 탭과 달리 이 화면을 선택했을 때만 통계 계산을 실행한다.
    try:
        period = st.selectbox("분석 기간", ["최근10회","최근30회","최근50회","최근100회","전체"])
        freq = frequency_table(df)
        st.bar_chart(freq.set_index("번호")[period])
        st.caption("미출현 상위")
        st.dataframe(
            absence_table(df).sort_values("미출현회차", ascending=False).head(15),
            hide_index=True, use_container_width=True
        )
        st.caption("동반출현 상위")
        st.dataframe(pair_frequency(df, 15), hide_index=True, use_container_width=True)
    except Exception as e:
        st.warning(f"통계 화면을 만들지 못했습니다: {e}")

elif section == "🏆 당첨 확인":
    if st.button("🔍 저장번호 당첨대조", use_container_width=True):
        try:
            st.success(f"{check_matches(DB_PATH)}건 확인 완료")
        except Exception as e:
            st.error(f"당첨대조 오류: {e}")
    try:
        hist = match_history(DB_PATH, 100)
        if hist.empty:
            st.info("대조 가능한 저장번호가 없습니다.")
        else:
            st.dataframe(hist, hide_index=True, use_container_width=True)
    except Exception as e:
        st.warning(f"당첨 기록을 읽지 못했습니다: {e}")

elif section == "📈 성과":
    try:
        perf = performance_by_strategy(DB_PATH)
        if perf.empty:
            st.info("추천번호와 실제 결과가 쌓이면 표시됩니다.")
        else:
            st.dataframe(perf, hide_index=True, use_container_width=True)
            st.bar_chart(perf.set_index("전략")["평균일치"])
    except Exception as e:
        st.warning(f"성과 화면을 만들지 못했습니다: {e}")

with st.expander("🧪 번호추출 진단 로그", expanded=False):
    diag_file = Path("lotto_generation_diag.log")
    if diag_file.exists():
        try:
            lines = diag_file.read_text(encoding="utf-8").splitlines()[-20:]
            st.code("\n".join(lines) if lines else "로그 없음")
        except Exception as e:
            st.caption(f"로그 읽기 실패: {e}")
    else:
        st.caption("아직 번호추출 로그가 없습니다.")

st.markdown("---")
st.caption("※ 통계점수·생년월일 개인화는 실제 당첨확률을 의미하지 않습니다.")
