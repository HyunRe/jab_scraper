import base64
import json
import os
import requests
from typing import List, Dict, Any, Tuple


class JobDeduplicator:
    def __init__(self, repo_slug: str = None, file_path: str = "data/processed_jobs.json", github_token: str = None):
        self.repo_slug = repo_slug or os.environ.get("GITHUB_REPOSITORY")  # 예: owner/repo
        self.file_path = file_path
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.processed_ids, self.file_sha = self._load_processed_ids()

    def _load_processed_ids(self) -> Tuple[set, str]:
        """GitHub API를 통해 repository의 processed_jobs.json 조회"""
        if not self.repo_slug or not self.github_token:
            print("[Deduplicator] GITHUB_REPOSITORY 또는 GITHUB_TOKEN 설정이 없어 중복 검사를 건너뜁니다.")
            return set(), None

        url = f"https://api.github.com/repos/{self.repo_slug}/contents/{self.file_path}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                content = base64.b64decode(data["content"]).decode("utf-8")
                ids = set(json.loads(content))
                print(f"[Deduplicator] GitHub에서 기존 처리된 공고 ID {len(ids)}건 조회 완료.")
                return ids, data.get("sha")
            elif res.status_code == 404:
                print(f"[Deduplicator] {self.file_path} 파일이 존재하지 않아 신규 생성 예정입니다.")
                return set(), None
            else:
                print(f"[Deduplicator] GitHub API 조회 실패 (Status: {res.status_code}): {res.text}")
                return set(), None
        except Exception as e:
            print(f"[Deduplicator] GitHub ID 목록 로드 중 오류 발생: {e}")
            return set(), None

    def filter_new_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """수집된 공고 중 이미 처리된 공고 제외"""
        new_jobs = []
        for job in jobs:
            if isinstance(job, dict):
                job_key = str(job.get("id") or job.get("url") or "")
            else:
                job_key = str(getattr(job, "id", None) or getattr(job, "url", None) or "")
            if job_key and job_key not in self.processed_ids:
                new_jobs.append(job)

        print(f"[Deduplicator] 전체 수집: {len(jobs)}건 | 신규 공고: {len(new_jobs)}건 (중복 {len(jobs) - len(new_jobs)}건 제외)")
        return new_jobs

    def save_processed_jobs(self, processed_jobs: List[Dict[str, Any]]):
        """평가까지 완료된 공고 ID를 추가하여 GitHub에 Commit & Push (API 호출)"""
        if not self.repo_slug or not self.github_token:
            print("[Deduplicator] GITHUB_REPOSITORY 또는 GITHUB_TOKEN 설정이 없어 GitHub 업데이트를 건너뜁니다.")
            return

        for job in processed_jobs:
            job_key = str(job.get("id") or job.get("url") or "")
            if job_key:
                self.processed_ids.add(job_key)

        url = f"https://api.github.com/repos/{self.repo_slug}/contents/{self.file_path}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        content_str = json.dumps(list(self.processed_ids), ensure_ascii=False, indent=2)
        encoded_content = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "chore: update processed job IDs from Lambda execution [skip ci]",
            "content": encoded_content
        }
        if self.file_sha:
            payload["sha"] = self.file_sha

        try:
            res = requests.put(url, headers=headers, json=payload)
            if res.status_code in (200, 201):
                print(f"[Deduplicator] GitHub 저장소의 {self.file_path} 파일 업데이트 완료.")
            else:
                print(f"[Deduplicator] GitHub 저장소 업데이트 실패 (Status: {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[Deduplicator] GitHub 저장소 파일 업데이트 중 예외 발생: {e}")