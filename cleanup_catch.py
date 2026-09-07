import json
import os
import re
import requests
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


def purge_catch_all():
    # 1. 노션 DB 전체 조회
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    pages = []
    has_more = True
    next_cursor = None

    print("🔍 노션 DB 전체 페이징 조회 중...")
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

    print(f"🔍 노션 DB 총 페이지: {len(pages)}건")

    catch_target_ids = set()
    deleted_notion_count = 0

    # 2. 노션 DB 내 캐치 데이터 전수 검사
    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})
        page_str = json.dumps(props, ensure_ascii=False).lower()

        # 캐치 데이터 판별 (URL, 플랫폼 이름, 캐치 키워드 포함 여부)
        if "catch" in page_str or "캐치" in page_str:
            # URL 등에서 추출 가능한 ID 세트 수집
            urls = re.findall(r"catch\.co\.kr/[^\s\"']+", page_str)
            for u in urls:
                # RecruitInfoDetails/{id} 패턴 매칭
                match = re.search(r"RecruitInfoDetails/([^/\?\"']+)", u)
                if match:
                    catch_target_ids.add(match.group(1).strip())

            # 노션 페이지 삭제 (archived)
            patch_url = f"https://api.notion.com/v1/pages/{page_id}"
            patch_res = requests.patch(
                patch_url, headers=HEADERS, json={"archived": True}
            )
            if patch_res.status_code == 200:
                print(f"🗑️ 캐치 노션 페이지 삭제 완료 (ID: {page_id})")
                deleted_notion_count += 1

    print(
        f"\n✅ 노션 DB 삭제 정제 완료: 총 {deleted_notion_count}건 처리됨"
    )

    # 3. processed_jobs.json 정제 (UUID 및 노션에서 발견된 캐치 ID 제거)
    if os.path.exists(PROCESSED_JOBS_PATH):
        with open(PROCESSED_JOBS_PATH, "r", encoding="utf-8") as f:
            try:
                processed_ids = json.load(f)
            except Exception:
                processed_ids = []

        before_count = len(processed_ids)

        # UUID 형식(8-4-4-4-12)이거나 노션 캐치 URL에서 발견된 ID 제거
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )

        updated_ids = [
            jid
            for jid in processed_ids
            if not uuid_pattern.match(str(jid).strip())
            and str(jid).strip() not in catch_target_ids
        ]

        removed_count = before_count - len(updated_ids)

        with open(PROCESSED_JOBS_PATH, "w", encoding="utf-8") as f:
            json.dump(updated_ids, f, ensure_ascii=False, indent=2)

        print(
            f"📂 processed_jobs.json 정제 완료 ({before_count}개 ➔"
            f" {len(updated_ids)}개, {removed_count}개 ID 제거됨)\n"
        )


if __name__ == "__main__":
    purge_catch_all()