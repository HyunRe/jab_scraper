from datetime import datetime, timedelta
import re
from typing import List
import requests

from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JumpitCollector(JobCollectorRepository):
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

    def supports(self, platform: str) -> bool:
        return platform == "점핏"

    def _format_deadline(self, deadline_str: str) -> str:
        """마감일 문자열을 '~월/일(요일)' 또는 '상시 채용' 형식으로 변환"""
        if not deadline_str:
            return "상시 채용"

        cleaned = deadline_str.strip()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        now = datetime.now()

        # 1. '오늘', '내일' 마감 키워드 처리
        if "오늘" in cleaned:
            return f"~{now.month}/{now.day}({weekdays[now.weekday()]})"
        if "내일" in cleaned:
            tomorrow = now + timedelta(days=1)
            return f"~{tomorrow.month}/{tomorrow.day}({weekdays[tomorrow.weekday()]})"

        # 2. D-day 패턴 처리 (예: 'D-1', 'D-day', 'D-0')
        match_dday = re.search(r"D-(day|DAY|\d+)", cleaned)
        if match_dday:
            d_val = match_dday.group(1).lower()
            days_left = 0 if d_val == "day" else int(d_val)
            target_date = now + timedelta(days=days_left)
            return f"~{target_date.month}/{target_date.day}({weekdays[target_date.weekday()]})"

        # 3. 상대 시간 및 상시 채용 키워드 처리
        if any(keyword in cleaned for keyword in ["전", "일 전", "시간 전", "분 전"]):
            return "상시 채용"

        if any(keyword in cleaned for keyword in ["상시", "채용시", "채용 시", "9999"]):
            return "상시 채용"

        # 4. 날짜 형식 파싱 시도
        try:
            # 연도가 포함된 형식 (예: 2026-04-15 또는 2026.04.15)
            match_full = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", cleaned)
            if match_full:
                year, month, day = map(int, match_full.groups())
                dt = datetime(year, month, day)
                return f"~{dt.month}/{dt.day}({weekdays[dt.weekday()]})"

            # 월/일만 있는 형식 (예: 04.15, 4/15, 4월 15일)
            match_md = re.search(r"(\d{1,2})[./월-]\s*(\d{1,2})일?", cleaned)
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
            jumpit_url = "https://api.jumpit.co.kr/api/positions?jobCategory=1&page=1&sort=relation"
            j_res = requests.get(jumpit_url, headers=self.headers, timeout=10)
            if j_res.status_code == 200:
                res_data = j_res.json() if isinstance(j_res.json(), dict) else {}
                position_list = (
                    res_data.get('result', {}).get('positions', [])
                    if isinstance(res_data.get('result'), dict)
                    else []
                )

                for item in position_list[:30]:
                    if not isinstance(item, dict):
                        continue

                    job_id = str(item.get('id', '') or '').strip()
                    if not job_id:
                        continue

                    title = str(item.get('title') or '제목 없음').strip()
                    company = str(item.get('companyName') or '기업명 미상').strip()

                    locations = item.get('locations') or []
                    loc_str = locations[0] if isinstance(locations, list) and locations else "상세 참조"

                    min_career = item.get('minCareer')
                    max_career = item.get('maxCareer')
                    exp_str = f"{min_career}~{max_career}년" if min_career is not None else "신입/경력 무관"

                    # 마감일 추출 및 포맷 통일 적용[cite: 8]
                    raw_closed_at = str(item.get('closedAt') or '').strip()
                    deadline = self._format_deadline(raw_closed_at)

                    jobs.append(
                        Job(
                            id=job_id,
                            platform="점핏",
                            title=title,
                            company=company,
                            url=f"https://www.jumpit.co.kr/position/{job_id}",
                            location=loc_str,
                            required_experience=exp_str,
                            deadline=deadline,
                        )
                    )
                print(f"[점핏] 수집 완료: {len(jobs)}건")
            else:
                print(f"[점핏] API 응답 에러 (Status: {j_res.status_code})")
        except Exception as e:
            print(f"[점핏] 수집 오류: {e}")

        return jobs

    def fetch_job_detail(self, job: Job) -> str:
        url = f"https://api.jumpit.co.kr/api/position/{job.id}"
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                res_data = res.json() if isinstance(res.json(), dict) else {}
                d = res_data.get('result', {}) if isinstance(res_data.get('result'), dict) else {}

                raw_tech_stacks = d.get('techStacks', []) or []
                parsed_stacks = []
                for stack in raw_tech_stacks:
                    if isinstance(stack, dict):
                        parsed_stacks.append(str(stack.get('stack') or stack.get('name') or ''))
                    elif isinstance(stack, str):
                        parsed_stacks.append(stack)

                return f"""
                [근무위치]: {job.location}
                [요구경력]: {job.required_experience}
                [마감일자]: {job.deadline}
                [주요업무]: {d.get('serviceInfo', '')} / {d.get('mainTask', '')}
                [자격요건]: {d.get('requirements', '')}
                [우대사항]: {d.get('preferredRequirements', '')}
                [기술스택]: {', '.join(filter(None, parsed_stacks))}
                """
        except Exception:
            pass

        return f"직무명: {job.title} / 회사명: {job.company} / 위치: {job.location} / 경력: {job.required_experience} / 마감일: {job.deadline}"