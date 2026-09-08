import os
from datetime import datetime, timedelta
import re
from typing import List
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class CatchCollector(JobCollectorRepository):
    def __init__(self, auth_token: str = None):
        self.auth_token = auth_token or os.getenv("CATCH_AUTH_TOKEN", "")
        self.base_url = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ko-KR,ko;q=0.9,en;q=0.8",
            "referer": "https://www.catch.co.kr/NCS/RecruitSearch",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "x-auth-token": self.auth_token,
            "x-is-pc": "true"
        }

    def supports(self, platform: str) -> bool:
        return platform == "캐치"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        now = datetime.now()

        # 1. '오늘 마감', '내일 마감' 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        elif "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. D-day 패턴 처리 (예: D-1, D-day, D-0)
        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        # 3. 상대 시간 및 상시 채용 표현 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 포맷 파싱
        try:
            # ISO 8601 포맷 (예: 2026-11-06T14:59:59.000Z)
            if "T" in cleaned:
                dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 연도가 포함된 날짜 (예: 2026-04-15, 2026.04.15)
            match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일 형식 (예: 04-15, 04/15)
            match_md = re.search(r'(\d{1,2})[./-](\d{1,2})', cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                dt = datetime(now.year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        # CI 환경 예외 처리
        if os.getenv("GITHUB_ACTIONS") == "true":
            print("\n[캐치] CI 환경(GitHub Actions) 감지: 테스트용 Mock 데이터를 반환합니다.")
            return [
                Job(
                    id="mock_1",
                    platform="캐치",
                    title="[CI Mock] 캐치 백엔드 개발자",
                    company="테스트 기업",
                    url="https://www.catch.co.kr/NCS/RecruitInfoDetails/mock_1",
                    location="서울 강남구",
                    required_experience="경력 무관",
                    deadline="상시 채용",
                )
            ]

        jobs: List[Job] = []
        try:
            params = {
                "Keyword": "백엔드",
                "JobCode": "",
                "Sido": "",
                "Career": "",
                "JCode": "",
                "Size": "",
                "EduLevel": "",
                "WorkPosition": "",
                "CompID": "",
                "GroupCode": "",
                "Sort": "0",
                "curpage": 1,
                "Priority": "",
                "pageSize": 30,
                "onRecruitYN": "Y",
                "ExceptIDList": ""
            }

            res = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                impersonate="chrome120",
                timeout=10
            )

            if res.status_code == 200:
                data = res.json() if isinstance(res.json(), dict) else {}
                recruit_list = data.get("recruitData", []) or []

                for item in recruit_list:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("RecruitID") or "").strip()
                    if not job_id:
                        continue

                    title = str(item.get("RecruitTitle") or "제목 없음").strip()
                    company = str(item.get("CompName") or "기업명 미상").strip()
                    location = str(item.get("WorkArea") or "상세 참조").strip()

                    # 경력 조건 매핑
                    career_code = str(item.get("CareerGubunCode") or item.get("ExperienceText") or "")
                    req_exp = career_code if career_code else "경력 무관"

                    # 마감일 (ApplyEndCode가 '상시채용'이면 이를 우선 사용, 아닐 경우 ApplyEndDatetime 파싱)
                    apply_end_code = str(item.get("ApplyEndCode") or "").strip()
                    raw_deadline = apply_end_code if apply_end_code == "상시채용" else str(item.get("ApplyEndDatetime") or "").strip()
                    deadline = self._format_deadline(raw_deadline)

                    # 캐치 웹 정식 상세 페이지 URL 규격 (RecruitInfoDetails + 복수 s)
                    job_url = f"https://www.catch.co.kr/NCS/RecruitInfoDetails/{job_id}"

                    # 디버그 프린트
                    print(f"[캐치 파싱] ID: {job_id} | 기업: {company} | 제목: {title} | 경력: '{req_exp}' | 마감일: '{deadline}'")

                    jobs.append(Job(
                        id=job_id,
                        platform="캐치",
                        title=title,
                        company=company,
                        url=job_url,
                        location=location,
                        required_experience=req_exp,
                        deadline=deadline
                    ))

                print(f"[캐치] 수집 완료: {len(jobs)}건")
            else:
                print(f"[캐치] API 응답 에러 (Status Code: {res.status_code})")

        except Exception as e:
            print(f"[캐치] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """캐치 공고 웹 페이지 HTML 파싱 기반 상세 내용 조회"""
        try:
            res = requests.get(
                job.url,
                headers={"User-Agent": self.headers["user-agent"]},
                impersonate="chrome120",
                timeout=10
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                detail_area = soup.select_one("div.re_view_box") or soup.select_one("div.tbl_detail")

                if detail_area:
                    content_text = detail_area.get_text(separator="\n", strip=True)
                    return f"[{job.title}] 상세 정보:\n{content_text[:1000]}"
        except Exception as e:
            print(f"[캐치] 상세 정보 조회 오류 ({job.id}): {e}")

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"