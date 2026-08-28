from datetime import datetime
from notion_client import Client
from typing import List, Dict, Any, Set


class NotionScripterNotifier:
    def __init__(self, notion_token: str, scripter_db_id: str):
        self.notion_token = notion_token
        self.notion = Client(auth=notion_token)
        self.scripter_db_id = scripter_db_id

    def fetch_existing_job_titles(self) -> Set[str]:
        """DB 1에 이미 등록된 모든 공고명([회사명] 공고명)을 조회하여 Set으로 반환"""
        if not self.scripter_db_id:
            return set()

        existing_titles = set()
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }

            has_more = True
            next_cursor = None

            while has_more:
                body: Dict[str, Any] = {
                    "page_size": 100
                }
                if next_cursor:
                    body["start_cursor"] = next_cursor

                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.scripter_db_id}/query",
                    headers=headers,
                    json=body
                )
                response = res.json()

                for page in response.get("results", []):
                    props = page.get("properties", {})
                    title_list = props.get("공고명", {}).get("title", [])
                    if title_list:
                        full_title = title_list[0].get("text", {}).get("content", "").strip()
                        if full_title:
                            existing_titles.add(full_title)

                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")

            print(f"[Notion DB 1] 기존 등록된 공고명 총 {len(existing_titles)}건 조회 완료")
        except Exception as e:
            print(f"[Notion DB 1] 기존 공고명 목록 조회 실패: {e}")

        return existing_titles

    def save_raw_jobs(self, jobs: List[Any], deduplicator=None) -> List[Dict[str, Any]]:
        """JobDeduplicator 및 노션 DB 1 공고명 중복 검사를 통과한 신규 공고만 적재"""
        if not self.scripter_db_id:
            raise ValueError("DB 1 (Scripter Database ID)가 설정되지 않았습니다.")

        # 1. GitHub 기반 1차 중복 제거 (Deduplicator)
        target_jobs = jobs
        if deduplicator:
            job_dicts = []
            for j in jobs:
                if isinstance(j, dict):
                    job_dicts.append(j)
                else:
                    job_dicts.append({
                        "id": getattr(j, "id", None),
                        "url": getattr(j, "url", None)
                    })

            filtered_dicts = deduplicator.filter_new_jobs(job_dicts)
            filtered_keys = {str(d.get("id") or d.get("url") or "") for d in filtered_dicts}

            target_jobs = []
            for j in jobs:
                j_key = str(j.get("id") or j.get("url") or "") if isinstance(j, dict) else str(
                    getattr(j, "id", None) or getattr(j, "url", None) or "")
                if j_key in filtered_keys:
                    target_jobs.append(j)

        # 2. 노션 DB 1 기존 공고명 기반 2차 중복 제거
        existing_titles = self.fetch_existing_job_titles()

        today_iso = datetime.now().strftime("%Y-%m-%d")
        saved_jobs = []

        for job in target_jobs:
            try:
                company = job.get("company", "회사명 미상") if isinstance(job, dict) else getattr(job, "company", "회사명 미상")
                title = job.get("title", "공고명 미상") if isinstance(job, dict) else getattr(job, "title", "공고명 미상")
                location = job.get("location", "정보 없음") if isinstance(job, dict) else getattr(job, "location", "정보 없음")
                req_exp = job.get("required_experience", "무관") if isinstance(job, dict) else getattr(job, "required_experience", "무관")
                deadline = job.get("deadline", "상시 채용") if isinstance(job, dict) else getattr(job, "deadline", "상시 채용")
                url = job.get("url", "") if isinstance(job, dict) else getattr(job, "url", "")

                title_text = f"[{company}] {title}"

                # 노션에 이미 존재하는 공고명일 경우 스킵
                if title_text in existing_titles:
                    print(f"[Notion DB 1] 스킵 (노션 공고명 중복): {title_text}")
                    continue

                new_page = self.notion.pages.create(
                    parent={"database_id": self.scripter_db_id},
                    properties={
                        "공고명": {
                            "title": [{"text": {"content": title_text}}]
                        },
                        "회사명": {
                            "rich_text": [{"text": {"content": company}}]
                        },
                        "근무위치": {
                            "rich_text": [{"text": {"content": location}}]
                        },
                        "요구경력": {
                            "rich_text": [{"text": {"content": req_exp}}]
                        },
                        "마감일": {
                            "rich_text": [{"text": {"content": deadline}}]
                        },
                        "수집일자": {
                            "date": {"start": today_iso}
                        },
                        "공고링크": {
                            "url": url
                        }
                    }
                )

                page_id = new_page.get("id")
                if page_id:
                    if isinstance(job, dict):
                        job["page_id"] = page_id
                    elif hasattr(job, "page_id"):
                        job.page_id = page_id

                # 중복 등록 방지를 위해 방금 추가한 공고명도 local set에 기록
                existing_titles.add(title_text)
                saved_jobs.append(job)
                print(f"[Notion DB 1] 공고 스크립트 적재 완료: {title_text}")
            except Exception as e:
                print(f"[Notion DB 1] 적재 오류: {e}")

        # 신규 적재건 저장 ID 동기화
        if deduplicator and saved_jobs:
            saved_dicts = []
            for j in saved_jobs:
                if isinstance(j, dict):
                    saved_dicts.append(j)
                else:
                    saved_dicts.append({
                        "id": getattr(j, "id", None),
                        "url": getattr(j, "url", None)
                    })
            deduplicator.save_processed_jobs(saved_dicts)

        return saved_jobs

    def _detect_platform_from_url(self, url: str) -> str:
        """공고 URL을 기반으로 구직 플랫폼 키값 추출"""
        if not url:
            return "기타"
        url_lower = url.lower()
        if "wanted.co.kr" in url_lower:
            return "WANTED"
        elif "jobkorea.co.kr" in url_lower:
            return "JOBKOREA"
        elif "saramin.co.kr" in url_lower:
            return "SARAMIN"
        elif "jumpit.co.kr" in url_lower:
            return "JUMPIT"
        elif "rallit.com" in url_lower:
            return "RALLIT"
        elif "jasoseol.com" in url_lower:
            return "JASOSEOL"
        return "기타"

    def fetch_jobs_by_status(self, status_field: str, status_value: str) -> List[Dict[str, Any]]:
        """DB 1에서 '분석' 컬럼 값이 지정된 상태(예: '요청')인 공고를 전체 페이징 순회하여 조회"""
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }

            results = []
            has_more = True
            next_cursor = None

            # 페이징 루프 처리
            while has_more:
                body: Dict[str, Any] = {
                    "page_size": 100,
                    "filter": {
                        "property": status_field,
                        "select": {
                            "equals": status_value
                        }
                    }
                }
                if next_cursor:
                    body["start_cursor"] = str(next_cursor)

                res = requests.post(
                    f"https://api.notion.com/v1/databases/{self.scripter_db_id}/query",
                    headers=headers,
                    json=body
                )
                response = res.json()

                for page in response.get("results", []):
                    props = page.get("properties", {})

                    # 회사명 추출
                    company_texts = props.get("회사명", {}).get("rich_text", [])
                    company = company_texts[0].get("text", {}).get("content", "") if company_texts else "회사명 미상"

                    # 공고명 추출
                    title_list = props.get("공고명", {}).get("title", [])
                    full_title = title_list[0].get("text", {}).get("content", "") if title_list else "공고명 미상"

                    # 회사명 접두어 안전 제거
                    title = full_title.replace(f"[{company}]", "").strip() if company != "회사명 미상" else full_title

                    # URL 추출 및 플랫폼 판단
                    url = props.get("공고링크", {}).get("url", "")
                    platform = self._detect_platform_from_url(url)

                    results.append({
                        "page_id": page["id"],
                        "company": company,
                        "title": title,
                        "url": url,
                        "platform": platform
                    })

                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")

            print(f"[Notion DB 1] '{status_field}' = '{status_value}' 검색 완료: 총 {len(results)}건 발견")
            return results
        except Exception as e:
            print(f"[Notion DB 1] 조회 오류: {e}")
            return []

    def update_status(self, page_id: str, status_field: str, status_value: str) -> bool:
        """DB 1의 특정 페이지 상태 변경"""
        try:
            properties = {
                status_field: {
                    "select": {
                        "name": status_value
                    }
                }
            }

            import requests
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            res = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"properties": properties}
            )

            # select 업데이트 실패 시 status 속성 타입으로 재시도
            if not res.ok:
                properties[status_field] = {"status": {"name": status_value}}
                res = requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": properties}
                )
            res.raise_for_status()

            print(f"[Notion DB 1] 페이지({page_id}) {status_field} 상태를 '{status_value}'(으)로 업데이트 완료")
            return True
        except Exception as e:
            print(f"[Notion DB 1] 페이지 상태 업데이트 오류 ({page_id}): {e}")
            return False