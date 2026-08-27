import os
from typing import Optional
from app.domain.interfaces import FileRepository
from app.infrastructure.resume_parser import ResumePlatformParser

class LocalFileRepository(FileRepository):
    def __init__(self, asset_dir: str = "assets"):
        self.asset_dir = asset_dir

    def read_asset(self, filename: str) -> str:
        filepath = os.path.join(self.asset_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def get_resume(self) -> str:
        """이력서 텍스트 로드"""
        return self.read_asset("resume.txt")

    def get_resume_parser(self) -> Optional[ResumePlatformParser]:
        """resume_platforms.txt 로드 후 플랫폼별 파서 객체 반환"""
        content = self.read_asset("resume_platforms.txt")
        if not content:
            content = self.read_asset("resume.txt")
        return ResumePlatformParser(content) if content else None

    def get_cover_letter_template(self) -> str:
        """cover_letter_template.txt (공통 작성 규칙 및 4개 항목/글자수 조건) 로드"""
        template = self.read_asset("cover_letter_template.txt")
        if not template:
            template = self.read_asset("cover_letter.txt")
        return template