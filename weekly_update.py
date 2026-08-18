
from updater import fetch_latest_official
from db import init_db, upsert_latest, check_matches, latest_draw_no

def main():
    init_db()
    before = latest_draw_no()
    latest = fetch_latest_official()
    upsert_latest(latest)
    checked = check_matches()
    print(f"DB 최신회차: {before} -> {latest_draw_no()}")
    print(f"공식 최신회차: {latest['회차']}")
    print(f"당첨대조 처리: {checked}건")

if __name__ == "__main__":
    main()
