
# 휴대폰용 배포 가이드

## 가장 쉬운 방법
Streamlit Community Cloud에 배포하면 휴대폰에 Python을 설치하지 않아도 됩니다.

1. GitHub 계정에서 새 저장소를 만듭니다.
2. 이 폴더의 파일 전체를 GitHub 저장소에 업로드합니다.
3. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
4. `Create app` 또는 앱 배포 메뉴에서 저장소를 선택합니다.
5. 실행 파일(entrypoint)을 `streamlit_app.py`로 지정합니다.
6. Deploy를 실행합니다.
7. 생성된 `https://...streamlit.app` 주소를 갤럭시에서 엽니다.

## 갤럭시 홈 화면에 추가
- Chrome 또는 삼성 인터넷에서 앱 주소를 엽니다.
- 브라우저 메뉴 → `홈 화면에 추가` 또는 `앱 설치`
- 이름: `로또당첨번호 생성기`

## 데이터 저장 주의
현재 SQLite 방식은 개인 MVP 테스트용입니다.
클라우드 호스팅 환경의 로컬 파일은 영구 저장소로 보장되지 않을 수 있습니다.
다음 단계에서는 Supabase/PostgreSQL 같은 외부 DB를 연결하면 추천번호와 결과를 안전하게 영구 저장할 수 있습니다.
