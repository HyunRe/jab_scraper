import os
from datetime import datetime
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class ZighangCollector(JobCollectorRepository):
    def __init__(self, headers: dict = None):
        self.base_url = "https://api.zighang.com/api/recruitments"
        self.headers = headers or {
            "accept": "application/json",
            "accept-language": "ko-KR,ko;q=0.9,en;q=0.8,en-US;q=0.7",
            "origin": "https://zighang.com",
            "referer": "https://zighang.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        }

    def supports(self, platform: str) -> bool:
        return platform == "직행"

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
            print("\n[직행] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="직행",
                    title="[CI Mock] 직행 백엔드 개발자",
                    company="테스트 기업",
                    url="https://zighang.com/recruitment/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "page": 0,
                "size": 30,
                "depthTwos": "서버_백엔드",
                "includeCareerOpen": "true",
                "sortCondition": "ZIGHANG_SCORE",
                "orderCondition": "DESC"
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                res_data = res.json() if isinstance(res.json(), dict) else {}
                payload = res_data.get("data", {}) if isinstance(res_data.get("data"), dict) else {}
                content = payload.get("content", []) if isinstance(payload.get("content"), list) else []

                for item in content:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("title") or item.get("recruitmentTitle") or "제목 없음").strip()

                    company_info = item.get("company") or item.get("companyName") or {}
                    if isinstance(company_info, dict):
                        company = str(company_info.get("name") or "기업명 미상").strip()
                    else:
                        company = str(company_info).strip() or "기업명 미상"

                    location = str(item.get("address") or item.get("location") or "상세 참조").strip()

                    # 경력 매핑
                    career_text = item.get("career") or item.get("experience")
                    req_exp = str(career_text).strip() if career_text else "경력 무관"

                    # 마감일 매핑
                    raw_deadline = item.get("deadline") or item.get("dueDate")
                    deadline = self._format_deadline(str(raw_deadline or ""))

                    job_url = f"https://zighang.com/recruitment/{job_id}"

                    jobs.append(Job(
                        id=job_id,
                        platform="직행",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[직행] 수집 완료: {len(jobs)}건")
            else:
                print(f"[직행] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[직행] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """직행 공고 상세 정보 조회"""
        try:
            detail_url = f"https://api.zighang.com/api/recruitments/{job.id}"
            res = requests.get(
                detail_url,
                headers=self.headers,
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                d = res.json().get("data", {}) if isinstance(res.json(), dict) else {}
                description = d.get("description") or d.get("content") or ""
                return f"[{job.title}] 상세 정보:\n{description[:1000]}"
        except Exception as e:
            print(f"[직행] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"