import re
from typing import Dict

class ResumePlatformParser:
    """resume_platforms.txt에서 사이트별 이력서 구성을 파싱하고 맞춤 템플릿을 추출하는 파서"""

    PLATFORM_KEY_MAP = {
        "WANTED": "1. WANTED (원티드)",
        "JOBKOREA": "2. JOBKOREA (잡코리아)",
        "SARAMIN": "3. SARAMIN (사람인)",
        "JUMPIT": "4. JUMPIT (점핏)",
        "RALLIT": "5. RALLIT (렐릿)",
        "INCRUIT": "6. INCRUIT (인크루트)",
        "LINKAREER": "7. LINKAREER (링커리어)",
    }

    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        self.master_data = self._extract_master_data()
        self.platform_sections = self._parse_sections()

    def _extract_master_data(self) -> str:
        match = re.search(r"\[통합 관리 데이터베이스 / Master Data\][\s\S]*?(?=={10,}|$)", self.raw_text)
        return match.group(0).strip() if match else ""

    def _parse_sections(self) -> Dict[str, str]:
        sections = {}
        blocks = re.split(r"={10,}", self.raw_text)
        for block in blocks:
            block_str = block.strip()
            for key_enum, header in self.PLATFORM_KEY_MAP.items():
                if header in block_str:
                    sections[key_enum] = block_str
        return sections

    def get_resume_for_platform(self, platform_name: str) -> str:
        norm_key = platform_name.upper()

        # 전용 이력서 서식이 없는 플랫폼들
        no_custom_resume_platforms = {
            "JASOSEOL", "REMEMBER", "JOBPLANET", "LINKEDIN", "ZIGHANG", "CATCH"
        }

        if norm_key in no_custom_resume_platforms:
            return self.master_data

        platform_section = self.platform_sections.get(norm_key, "")
        return f"{self.master_data}\n\n{platform_section}".strip()