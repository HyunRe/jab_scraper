from datetime import datetime, timedelta, timezone, time
import re
from typing import List
import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JasoseolCollector(JobCollectorRepository):
    def __init__(self):
        self.url = "https://jasoseol.com/employment/calendar_list.json"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": "https://jasoseol.com/",
        }

    def supports(self, platform: str) -> bool:
        return platform == "자소설닷컴"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 형식으로 파싱 및 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        now = datetime.now()

        # 1. 오늘/내일 키워드 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        if "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. D-day 패턴 처리 (예: D-day, D-1, D-14)
        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        # 3. 상대 시간 표현('3일 전' 등) 및 상시 채용 문구 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 포맷 파싱
        try:
            # ISO 포맷 또는 연도 포함 날짜 (예: 2026-04-15)
            match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일 형식 (예: 04/15, 04-15, 4월 15일)
            match_md = re.search(r'(\d{1,2})[./월-]\s*(\d{1,2})일?', cleaned)
            if match_md:
                month, day = map(int, match_md.groups())
                dt = datetime(now.year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"
        except Exception:
            pass

        return cleaned if cleaned else "상시 채용"

    def fetch_jobs(self) -> List[Job]:
        jobs = []
        try:
            now = datetime.now(timezone.utc)
            start_time = (now - timedelta(days=15)).strftime("%Y-%m-%dT15:00:00.000Z")
            end_time = (now + timedelta(days=20)).strftime("%Y-%m-%dT15:00:00.000Z")

            res = requests.post(
                self.url,
                headers=self.headers,
                json={"start_time": start_time, "end_time": end_time},
                timeout=10,
            )

            if res.status_code == 200:
                data = res.json()
                employments = data.get("employment", []) if isinstance(data, dict) else []
                keywords = ["백엔드", "backend", "server", "java", "spring", "서버", "개발"]

                for item in employments:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get("id", "")).strip()
                    if not job_id:
                        continue

                    # [방어 로직] 안전한 기본값 설정
                    title = str(item.get("title") or "제목 없음").strip()
                    company_name = str(item.get("name") or "기업명 미상").strip()

                    if any(kw.lower() in (title + company_name).lower() for kw in keywords):
                        deadline_raw = str(item.get("end_time") or "")
                        # 날짜 포맷 통일 함수 적용 전 ISO 포맷 문자열 정리 (예: '2026-04-15T15:00:00.000Z')
                        formatted_raw = deadline_raw.split(".")[0].replace("T", " ") if deadline_raw else ""
                        deadline = self._format_deadline(formatted_raw)

                        jobs.append(
                            Job(
                                id=job_id,
                                platform="자소설닷컴",
                                title=title,
                                company=company_name,
                                url=f"https://jasoseol.com/recruit/{job_id}",
                                location="상세 참조",
                                required_experience="신입/경력 공채",
                                deadline=deadline,
                            )
                        )

                print(f"[자소설닷컴] 수집 완료: {len(jobs)}건")
        except Exception as e:
            print(f"[자소설닷컴] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        """공고 상세 내용을 조회합니다."""
        return f"[{job.title}] 상세 내용 및 자소서 항목"