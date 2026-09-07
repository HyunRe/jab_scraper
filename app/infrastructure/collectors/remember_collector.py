import os
from datetime import datetime
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class RememberCollector(JobCollectorRepository):
    def __init__(self, auth_token: str = None):
        self.url = "https://career-api.rememberapp.co.kr/job_postings/search"
        token = auth_token or "e1d61317e90dac2966d080621a4c1805"
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Token token={token}",
            "content-type": "application/json",
            "origin": "https://career.rememberapp.co.kr",
            "referer": "https://career.rememberapp.co.kr/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        }

    def supports(self, platform: str) -> bool:
        return platform == "리멤버"

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
            # 연도가 포함된 형식 (예: 2026-04-15T23:59:59 또는 2026.04.15)
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
        # CI 환경 예외 처리 (타 수집기들과 동일 패턴)
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[리멤버] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="리멤버",
                    title="[CI Mock] 리멤버 백엔드 개발자",
                    company="테스트 기업",
                    url="https://career.rememberapp.co.kr/job/postings/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            payload = {
                "job_posting_list_ab_test": "A",
                "new_function_score": False,
                "page": 1,
                "per": 30,
                "search": {
                    "include_applied_job_posting": False,
                    "keyword": "백엔드"
                },
                "sort": "recommended"
            }

            res = requests.post(
                self.url,
                headers=self.headers,
                json=payload,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                res_data = res.json() if isinstance(res.json(), dict) else {}
                postings = res_data.get("data", []) if isinstance(res_data.get("data"), list) else []

                for item in postings:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("title") or "제목 없음").strip()

                    org = item.get("organization", {}) or {}
                    company = str(org.get("name") or "기업명 미상").strip()

                    location = str(item.get("normalized_address") or "상세 참조").strip()

                    min_exp = item.get("min_experience")
                    max_exp = item.get("max_experience")
                    if min_exp is not None and max_exp is not None:
                        req_exp = f"{min_exp}~{max_exp}년"
                    elif min_exp is not None:
                        req_exp = f"{min_exp}년 이상"
                    else:
                        req_exp = "경력 무관"

                    # 마감일 추출 및 포맷 통일 적용
                    raw_close_at = str(item.get("close_at") or "").strip()
                    deadline = self._format_deadline(raw_close_at)

                    job_url = f"https://career.rememberapp.co.kr/job/postings/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="리멤버",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[리멤버] 수집 완료: {len(jobs)}건")
            else:
                print(f"[리멤버] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[리멤버] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """리멤버 공고 상세 정보 조회 API 파싱"""
        try:
            detail_url = f"https://career-api.rememberapp.co.kr/job_postings/{job.id}"
            res = requests.get(
                detail_url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                d = res.json().get("data", {}) if isinstance(res.json(), dict) else {}
                return f"""
                [근무위치]: {job.location}
                [요구경력]: {job.required_experience}
                [마감일자]: {job.deadline}
                [주요업무]: {d.get('job_description', '')}
                [자격요건]: {d.get('qualifications', '')}
                [우대사항]: {d.get('preferred_qualifications', '')}
                [채용절차]: {d.get('recruiting_process', '')}
                """
        except Exception as e:
            print(f"[리멤버] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"