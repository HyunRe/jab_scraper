import json
import os
import requests
from curl_cffi import requests as cffi_requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_JOB_SCRIPTER_DB_ID")
PROCESSED_JOBS_PATH = os.path.join("data", "processed_jobs.json")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def get_all_jobplanet_target_ids():
    """잡플래닛 API의 전체 페이지를 순회하여 현재 수집 가능한 모든 공고 ID를 추출"""
    print("🔍 잡플래닛 API 전체 페이지 조회 중...")
    api_url = "https://www.jobplanet.co.kr/api/v3/job/postings"
    jp_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.jobplanet.co.kr/job",
        "jp-os-type": "web",
        "jp-ssr-auth": (
            "jobplanet_desktop_ssr_1d6f8a5f219176accbb8fe051729fc6a"
        ),
    }

    jp_ids = set()
    page = 1

    while True:
        params = {
            "occupation_level2": "11904",  # 백엔드/개발 세부 카테고리
            "order_by": "aggressive",
            "page": page,
            "page_size": 100,  # 1회 최대 요청 건수
        }

        try:
            res = cffi_requests.get(
                api_url,
                headers=jp_headers,
                params=params,
                impersonate="chrome120",
                timeout=10,
            )

            if res.status_code != 200:
                print(
                    f"⚠️ 잡플래닛 API 응답 이상 (Status Code: {res.status_code})"
                )
                break

            recruits = res.json().get("data", {}).get("recruits", [])
            if not recruits:
                # 더 이상 가져올 공고가 없으면 페이징 종료
                break

            for item in recruits:
                if item.get("id"):
                    jp_ids.add(str(item.get("id")).strip())

            print(f"  - {page}페이지 수집 완료 (현재 누적 ID: {len(jp_ids)}개)")
            page += 1

        except Exception as e:
            print(f"⚠️ 잡플래닛 API 조회 중 오류 발생: {e}")
            break

    print(f"🎯 잡플래닛 전체 타겟 ID 총 {len(jp_ids)}개 추출 완료\n")
    return jp_ids


def clean_jobplanet_everywhere():
    # 1. 잡플래닛 API 전체 공고 ID 가져오기
    jp_ids = get_all_jobplanet_target_ids()

    # 2. 노션 DB 전체 페이징 조회 및 잡플래닛 항목 삭제
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    pages = []
    has_more = True
    next_cursor = None

    print("🔍 노션 DB 전체 조회 중...")
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        res = requests.post(url, headers=HEADERS, json=payload)
        if res.status_code != 200:
            print(f"❌ 노션 DB 조회 실패: {res.text}")
            break

        data = res.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    print(f"🔍 노션 DB 전체 페이지: {len(pages)}건")

    deleted_notion_count = 0
    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})

        # 노션 페이지 JSON 전체를 문자열로 변환 후 판별
        page_str = json.dumps(props, ensure_ascii=False).lower()

        # 조건 1: 노션 속성에 'jobplanet' 또는 '잡플래닛' 텍스트 포함 여부
        is_jp = "jobplanet" in page_str or "잡플래닛" in page_str

        # 조건 2: 추출한 잡플래닛 ID 중 노션 데이터에 포함된 것이 있는지 확인
        if not is_jp:
            for jid in jp_ids:
                if jid in page_str:
                    is_jp = True
                    break

        if is_jp:
            patch_url = f"https://api.notion.com/v1/pages/{page_id}"
            patch_res = requests.patch(
                patch_url, headers=HEADERS, json={"archived": True}
            )
            if patch_res.status_code == 200:
                print(f"🗑️ 잡플래닛 노션 페이지 삭제 완료 (ID: {page_id})")
                deleted_notion_count += 1
            else:
                print(f"❌ 노션 삭제 실패 ({page_id}): {patch_res.text}")

    print(f"✅ 노션 DB 삭제 정제 완료: 총 {deleted_notion_count}건 처리됨")

    # 3. data/processed_jobs.json 내 잡플래닛 ID 제거
    if os.path.exists(PROCESSED_JOBS_PATH):
        with open(PROCESSED_JOBS_PATH, "r", encoding="utf-8") as f:
            try:
                processed_ids = json.load(f)
            except Exception:
                processed_ids = []

        before_count = len(processed_ids)

        # 추출한 잡플래닛 전체 ID 세트에 들어있는 ID만 제거
        updated_ids = [
            jid for jid in processed_ids if str(jid).strip() not in jp_ids
        ]
        removed_count = before_count - len(updated_ids)

        with open(PROCESSED_JOBS_PATH, "w", encoding="utf-8") as f:
            json.dump(updated_ids, f, ensure_ascii=False, indent=2)

        print(
            f"📂 processed_jobs.json 정제 완료 ({before_count}개 ➔"
            f" {len(updated_ids)}개, {removed_count}개 ID 제거됨)\n"
        )
    else:
        print("⚠️ processed_jobs.json 파일이 존재하지 않습니다.\n")

    print("✨ 모든 정제 작업이 완료되었습니다!")


if __name__ == "__main__":
    clean_jobplanet_everywhere()