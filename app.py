
import streamlit as st
import pandas as pd
from pathlib import Path
from analytics import load_file, frequency_table, absence_table, pair_frequency, summary, validate
from generator import generate_candidates, select_diverse_top, simple_backtest
from updater import fetch_latest_official
from personalizer import birth_based_weights, favorite_numbers_from_birth
from db import init_db,upsert_draws,upsert_latest,load_draws,latest_draw_no,save_recommendations,load_recommendations,check_matches,performance_by_strategy,match_history

DB_PATH="lotto_app.db"
init_db(DB_PATH)
st.set_page_config(page_title="로또당첨번호 생성기",page_icon="🎯",layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1rem;max-width:1120px}
div[data-testid="stMetric"]{border:1px solid #ddd;padding:10px;border-radius:12px}
.stButton button{min-height:48px;border-radius:12px;font-weight:700}
@media(max-width:700px){.block-container{padding-left:.55rem;padding-right:.55rem}h1{font-size:1.75rem!important}}
</style>
""",unsafe_allow_html=True)

st.title("🎯 로또당첨번호 생성기")
st.caption("4단계 · 지속사용형 MVP")
st.warning("통계점수·사주 개인화는 실제 당첨확률이 아닙니다. 모든 6개 조합의 추첨확률은 동일합니다.")

with st.sidebar:
    st.header("데이터 관리")
    uploaded=st.file_uploader("과거 당첨번호 CSV/XLSX",type=["csv","xlsx","xls"])
    if uploaded is not None:
        try:
            udf=load_file(uploaded)
            issues=validate(udf)
            if issues: st.warning("검증 경고: "+" / ".join(issues[:3]))
            if st.button("업로드 자료를 DB에 저장"):
                n=upsert_draws(udf,DB_PATH,source="upload")
                st.success(f"{n}개 회차 저장/갱신")
        except Exception as e:
            st.error(f"파일 오류: {e}")
    if st.button("공식 최신 회차 확인·저장"):
        try:
            latest=fetch_latest_official()
            upsert_latest(latest,DB_PATH)
            check_matches(DB_PATH)
            st.success(f"{latest['회차']}회 저장 및 당첨대조 완료")
        except Exception as e:
            st.error(f"자동 확인 실패: {e}")
            st.info("공식 통계 CSV/XLSX 업로드 방식으로 계속 사용할 수 있습니다.")

df=load_draws(DB_PATH)
if df.empty:
    st.info("왼쪽에서 과거 당첨번호 파일을 업로드해 DB를 먼저 채워주세요.")
    st.stop()

s=summary(df)
c1,c2,c3,c4=st.columns(4)
c1.metric("DB 회차",f"{len(df):,}")
c2.metric("최신 회차",int(df["회차"].max()))
c3.metric("평균 번호합",s["평균합계"])
c4.metric("추천 저장",len(load_recommendations(DB_PATH,limit=100000)))

tabs=st.tabs(["🎲 생성","✅ 당첨대조","📈 성과판","🔢 통계","🧪 백테스트","🗄 DB"])

with tabs[0]:
    c1,c2,c3=st.columns(3)
    strategy=c1.selectbox("전략",["혼합형","균형형","빈도형","미출현형","완전랜덤"])
    games=c2.selectbox("게임 수",[5,10,15,20],index=0)
    candidates_n=c3.selectbox("후보 수",[2000,5000,10000,20000],index=2)
    target_draw=st.number_input("대상 회차",min_value=1,value=int(df["회차"].max())+1,step=1)
    include=st.multiselect("반드시 포함할 번호",list(range(1,46)))
    exclude=st.multiselect("제외할 번호",[n for n in range(1,46) if n not in include])
    max_overlap=st.slider("게임 간 최대 중복 번호",1,5,3)
    personal_on=st.toggle("사주·생년월일 개인화(재미용)")
    personal_weights=None
    if personal_on:
        birth_text=st.text_input("생년월일",placeholder="예: 음력 1967-12-19")
        if birth_text:
            personal_weights=birth_based_weights(birth_text)
            st.caption("개인화 선호수: "+" · ".join(map(str,favorite_numbers_from_birth(birth_text))))
    seed_text=st.text_input("재현용 시드(선택)",value="")
    seed=None if not seed_text.strip() else int(seed_text)

    if st.button("🎯 추천번호 생성",use_container_width=True):
        try:
            cand,_=generate_candidates(df,strategy,candidates_n,seed,include=include,exclude=exclude,personal_weights=personal_weights)
            st.session_state["last_picks"]=select_diverse_top(cand,games,max_overlap)
            st.session_state["last_meta"]={"target_draw":int(target_draw),"strategy":strategy,"birth_mode":personal_on,"include":include,"exclude":exclude}
        except Exception as e:
            st.error(str(e))

    if "last_picks" in st.session_state:
        picks=st.session_state["last_picks"]
        st.dataframe(picks,hide_index=True,use_container_width=True)
        c1,c2=st.columns(2)
        with c1:
            if st.button("💾 이 추천번호 저장",use_container_width=True):
                m=st.session_state["last_meta"]
                ids=save_recommendations(picks,m["target_draw"],m["strategy"],DB_PATH,birth_mode=m["birth_mode"],include_numbers=m["include"],exclude_numbers=m["exclude"])
                st.success(f"{len(ids)}게임 저장 완료")
        with c2:
            st.download_button("CSV 다운로드",picks.to_csv(index=False,encoding="utf-8-sig").encode("utf-8-sig"),"lotto_recommendations.csv","text/csv",use_container_width=True)

with tabs[1]:
    if st.button("🔍 현재 DB 기준으로 전체 당첨대조"):
        st.success(f"{check_matches(DB_PATH)}건 대조 완료")
    hist=match_history(DB_PATH)
    if hist.empty: st.info("아직 당첨번호가 확정된 저장 추천이 없습니다.")
    else: st.dataframe(hist,hide_index=True,use_container_width=True)

with tabs[2]:
    perf=performance_by_strategy(DB_PATH)
    if perf.empty: st.info("추천번호 저장 후 해당 회차 당첨번호가 DB에 들어오면 성과가 쌓입니다.")
    else:
        st.dataframe(perf,hide_index=True,use_container_width=True)
        st.bar_chart(perf.set_index("전략")["평균일치"])
    st.caption("과거 성과 기록이며 미래 성과를 보장하지 않습니다.")

with tabs[3]:
    c1,c2=st.columns(2)
    with c1:
        period=st.selectbox("빈도 기간",["전체","최근100회","최근50회","최근30회","최근10회"])
        freq=frequency_table(df)
        st.bar_chart(freq.set_index("번호")[period])
    with c2:
        st.dataframe(absence_table(df).sort_values("미출현회차",ascending=False).head(20),hide_index=True,use_container_width=True)
    st.dataframe(pair_frequency(df,30),hide_index=True,use_container_width=True)

with tabs[4]:
    test_draws=st.selectbox("검증 회차 수",[10,20,30],index=0)
    if st.button("4개 전략 비교"):
        rows=[]
        for stg in ["혼합형","균형형","빈도형","미출현형"]:
            bt=simple_backtest(df,stg,test_draws=test_draws,candidates_per_draw=1000)
            if not bt.empty:
                rows.append({"전략":stg,"평균 최대 일치":round(bt["최대일치개수"].mean(),3),"3개 이상 회차":int((bt["최대일치개수"]>=3).sum()),"최고 일치":int(bt["최대일치개수"].max())})
        st.dataframe(pd.DataFrame(rows).sort_values(["평균 최대 일치","최고 일치"],ascending=False),hide_index=True,use_container_width=True)

with tabs[5]:
    st.write(f"DB 파일: `{DB_PATH}`")
    st.write(f"최신 저장 회차: **{latest_draw_no(DB_PATH)}**")
    st.dataframe(df.sort_values("회차",ascending=False).head(100),hide_index=True,use_container_width=True)
    st.subheader("저장 추천")
    st.dataframe(load_recommendations(DB_PATH,limit=200),hide_index=True,use_container_width=True)
    if Path(DB_PATH).exists():
        st.download_button("SQLite DB 백업 다운로드",Path(DB_PATH).read_bytes(),"lotto_app_backup.db","application/octet-stream")
