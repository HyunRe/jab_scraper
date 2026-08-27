import requests
from typing import List
from app.domain.models import Job
from app.domain.interfaces import JobCollectorRepository


class JumpitCollector(JobCollectorRepository):
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def supports(self, platform: str) -> bool:
        return platform == "점핏"

    def fetch_jobs(self) -> List[Job]:
        jobs = []
        try:
            jumpit_url = "https://api.jumpit.co.kr/api/positions?jobCategory=1&page=1&sort=relation"
            j_res = requests.get(jumpit_url, headers=self.headers, timeout=10)
            if j_res.status_code == 200:
                res_data = j_res.json() if isinstance(j_res.json(), dict) else {}
                position_list = res_data.get('result', {}).get('positions', []) if isinstance(res_data.get('result'),
                                                                                              dict) else []

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

                    closed_at = str(item.get('closedAt') or '상시 채용').strip()

                    jobs.append(Job(
                        id=job_id,
                        platform="점핏",
                        title=title,
                        company=company,
                        url=f"https://www.jumpit.co.kr/position/{job_id}",
                        location=loc_str,
                        required_experience=exp_str,
                        deadline=closed_at
                    ))
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