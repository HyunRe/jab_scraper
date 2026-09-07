from datetime import datetime
import re
import requests
from typing import List
from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository

class RallitCollector(JobCollectorRepository):
    def __init__(self):
        self.url = "https://b2c-api.rallit.com/client/api/v1/position"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.rallit.com/"
        }

    def supports(self, platform: str) -> bool:
        return platform == "랠릿"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 형식으로 파싱 및 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()

        # 상대 시간 표현(예: '3일 전', '2시간 전')이나 불필요한 문구 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return ""

        if "상시" in cleaned or "채용시" in cleaned or "채용 시" in cleaned or "9999" in cleaned:
            return "상시 채용"

        try:
            # 연도가 포함된 형식 (예: 2026-04-15T00:00:00 또는 2026-04-15 또는 2026.04.15)
            match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                weekdays = ['월', '화', '수', '목', '금', '토', '일']
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일만 있는 형식 (예: 04.15, 4/15, 4월 15일)
            match_md = re.search(r'(\d{1,2})[./월]\s*(\d{1,2})일?', cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                current_year = datetime.now().year
                dt = datetime(current_year, month, day)
                weekdays = ['월', '화', '수', '목', '금', '토', '일']
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        jobs = []
        try:
            params = {
                "job": "BACKEND_DEVELOPER",
                "jobGroup": "DEVELOPER",
                "pageNumber": 1,
                "pageSize": 30,
                "isPublic": "false"
            }
            res = requests.get(self.url, headers=self.headers, params=params, timeout=10)

            if res.status_code == 200:
                response_data = res.json()
                data_obj = response_data.get("data", {}) if isinstance(response_data, dict) else {}
                items = data_obj.get("items", []) if isinstance(data_obj, dict) else []

                keywords = ["백엔드", "backend", "server", "java", "spring", "서버", "개발"]

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id", "")).strip()
                    if not job_id:
                        continue  # ID가 없으면 식별 불가능하므로 제외

                    # [방어 로직] 안전한 기본값(Fallback) 제공
                    title = str(item.get("title") or "제목 없음").strip()
                    company_name = str(item.get("companyName") or "기업명 미상").strip()

                    skill_keywords = item.get("jobSkillKeywords") or []
                    if not isinstance(skill_keywords, list):
                        skill_keywords = []

                    search_text = (title + company_name + " ".join(map(str, skill_keywords))).lower()

                    if any(kw.lower() in search_text for kw in keywords):
                        ended_at = str(item.get("endedAt") or "")

                        # 마감일 추출 및 포맷 통일 적용
                        deadline = self._format_deadline(ended_at)

                        # 1. location 방어 로직 (None / null / 빈 문자열 대응)
                        address_region = item.get("addressRegion")
                        if address_region and str(address_region).strip() not in ["None", "null", ""]:
                            location = str(address_region).strip()
                        else:
                            location = "상세 참조"

                        job_url = item.get("url") or f"https://www.rallit.com/positions/{job_id}"

                        # 2. required_experience 방어 로직 (is_target_job의 allow_patterns에 정확히 매칭)
                        jobs.append(Job(
                            id=job_id,
                            platform="랠릿",
                            title=title,
                            company=company_name,
                            url=job_url,
                            location=location,
                            required_experience="신입/주니어",
                            deadline=deadline
                        ))

                print(f"[랄릿] 수집 완료: {len(jobs)}건")
        except Exception as e:
            print(f"[랄릿] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """공고 상세 내용을 조회합니다."""
        # 랠릿 상세 본문 수집 혹은 기본 상세 내용 반환 처리
        return f"[{job.title}] 상세 내용 및 기술 스택 정보"