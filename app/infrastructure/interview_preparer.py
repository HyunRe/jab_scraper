import json
import time
from google import genai
from google.genai import types
from json_repair import repair_json
from pydantic import BaseModel, Field


# 1. 질문과 답변 구조를 정의하는 내부 스키마
class InterviewQuestionItem(BaseModel):
    question: str = Field(description="심화 기술 면접 예상 질문")
    summary: str = Field(description="1문장 핵심 답변 (결론 및 방향성)")
    keywords: list[str] = Field(description="답변 시 반드시 언급해야 할 핵심 기술 키워드 3~4개")
    experience_point: str = Field(description="이력서/프로젝트 경험과 연계하여 언급할 포인트 또는 메모 가이드")


# 2. 메인 반환 스키마
class InterviewPrepSchema(BaseModel):
    interview_questions: list[InterviewQuestionItem] = Field(description="JD 및 이력서 기반 심화 기술 면접 예상 질문 10선과 핵심 답변 구조")
    coding_test_prep: str = Field(description="맞춤형 알고리즘 문제 해결 및 SQL 튜닝 준비 지침")


class InterviewPreparer:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3.5-flash"

    def generate_interview_prep(self, company: str, job_title: str, jd_text: str, resume_text: str) -> InterviewPrepSchema:
        prompt = f"""
        지원자가 [{company}]의 [{job_title}] 직무에 실제 서류 지원을 완료했습니다.
        합격을 위한 심화 기술 면접 질문 10개 및 각 질문에 대한 핵심 답변 가이드(핵심 요약, 필수 키워드, 경험 연계 포인트)와 코딩테스트 및 SQL 튜닝 준비 지침을 작성하세요.

        [채용 공고 상세 (JD)]
        {jd_text}

        [지원자 이력서]
        {resume_text}

        [수행 작업]
        1. 공고의 주요 백엔드 기술 스택과 지원자의 실제 경험을 대조하여 면접에서 나올 수 있는 심화 질문 10개를 선정하세요.
        2. 각 질문마다 지원자가 면접에서 말할 수 있는 '핵심 요약(1문장)', '필수 포함 키워드(3~4개)', '이력서 기반 연계 포인트/메모'를 가이드라인으로 함께 제시하세요.
        3. 이 회사의 기술 과제 해결에 필요한 핵심 알고리즘 주제와 SQL 튜닝 준비 지침을 상세히 기술하세요.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=InterviewPrepSchema
        )

        time.sleep(3)
        res = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )

        try:
            return InterviewPrepSchema.model_validate_json(res.text)
        except Exception:
            repaired = repair_json(res.text, return_objects=True)
            return InterviewPrepSchema(**repaired)