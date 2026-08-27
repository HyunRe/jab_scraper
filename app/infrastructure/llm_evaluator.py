import json
import re
import time
from typing import Tuple, Optional
from google import genai
from google.genai import types
from json_repair import repair_json
from pydantic import BaseModel, Field

from app.domain.models import Job, JobEvaluation
from app.domain.interfaces import LLMEvaluator

# 1. Pydantic을 이용한 Response Schema 정의 (Gemini 출력 강제용)
class EvaluationSchema(BaseModel):
    score: str = Field(description="'상', '중', '하' 중 하나")
    match_or_lack_reason: str = Field(description="JD 요구사항 대비 강점 및 부족한 점 분석")
    matching_tech_stacks: list[str] = Field(description="공고와 일치하는 주요 기술 스택")
    customized_resume_summary_html: str = Field(
        description="제시된 구직 사이트({job.platform}) 전용 이력서 서식을 엄격히 준수하여 각색된 이력서 핵심 내용 (Markdown 양식)"
    )
    customized_cover_letter_html: str = Field(
        description="회사의 JD 및 요구 인재상에 맞춰 전면 각색된 자소서 전체 내용 (Markdown 양식, 강조는 **내용**, 취소는 ~~내용~~ 적용)"
    )

class GeminiLLMEvaluator(LLMEvaluator):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.client = genai.Client(api_key=api_key)
        self.model_name = self._get_available_model()

    def _get_available_model(self) -> str:
        """현재 계정에서 지원하는 최신 Flash 모델을 탐색합니다."""
        try:
            models = list(self.client.models.list())
            priority_keywords = ['3.5-flash', '3.6-flash', '3.1-flash-lite', 'flash']

            for keyword in priority_keywords:
                for m in models:
                    model_id = m.name.replace('models/', '')
                    if keyword in model_id.lower():
                        print(f"[LLM] 동적 선택된 모델: {model_id}")
                        return model_id

            if models:
                selected = models[0].name.replace('models/', '')
                return selected
        except Exception as e:
            print(f"[LLM] 모델 목록 조회 실패, 기본값 사용: {e}")

        return 'gemini-3.5-flash'

    def _call_api_with_retry(self, prompt: str, config: Optional[types.GenerateContentConfig] = None, max_retries: int = 5) -> str:
        """Rate Limit(429) 및 503 오류 발생 시 재시도하는 래퍼 함수"""
        delay = 10
        if config is None:
            config = types.GenerateContentConfig(response_mime_type="application/json")

        for attempt in range(max_retries):
            try:
                # RPM 제한 방지를 위한 호출 직전 기본 대기
                time.sleep(4)
                res = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                return res.text
            except Exception as e:
                err_str = str(e)
                if (
                        "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                    print(f"[LLM] API 제한/과부하 발생 ({err_str[:50]}...). {delay}초 후 재시도합니다 ({attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e
        raise RuntimeError("LLM API 재시도 횟수 초과")

    def _clean_json_text(self, text: str) -> str:
        """응답 텍스트에서 마크다운 백틱 및 JSON 외곽 텍스트 정제"""
        cleaned = text.strip()
        # 마크다운 코드 블록 제거
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)

        # 가장 첫 '{' 부터 가장 마지막 '}' 까지만 정확히 포착
        first_idx = cleaned.find('{')
        last_idx = cleaned.rfind('}')

        if first_idx != -1 and last_idx != -1 and last_idx > first_idx:
            cleaned = cleaned[first_idx:last_idx + 1]

        return cleaned.strip()

    def _safe_parse_json(self, json_text: str) -> dict:
        """json.loads 실패 시 json_repair로 보정 파싱하는 헬퍼 함수"""
        try:
            return json.loads(json_text)
        except Exception:
            # json_repair 결과가 dict가 아닐 경우를 대비한 안전 장치
            repaired = repair_json(json_text, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
            # 만약 dict가 아닌 다른 타입(list 등)으로 복구되었다면 빈 딕셔너리 반환 또는 변환
            return {}

    def evaluate_basic(self, job: Job) -> str:
        """공고의 기본 정보(제목, 회사명 등)만 활용하여 1차 선별('상', '중', '하')을 수행합니다."""
        prompt = f"""
        채용 공고의 기본 정보를 보고 지원자의 백엔드 역량 관점에서 적합도를 '상', '중', '하' 중 하나로만 평가하여 응답하세요.
        다른 설명이나 마크다운 없이 오직 글자 하나만 출력하세요. (예: 상)

        회사명: {job.company}
        직무: {job.title}
        근무위치: {job.location}
        요구경력: {job.required_experience}
        플랫폼: {job.platform}
        """
        try:
            config = types.GenerateContentConfig(response_mime_type="text/plain")
            res_text = self._call_api_with_retry(prompt, config=config)
            score = res_text.strip()

            if score in ['상', '중', '하']:
                return score
            return '상'
        except Exception as e:
            print(f"[LLM] 1단계 기본 평가 중 예외 발생, 기본값 '상' 처리: {e}")
            return '상'

    def select_domain_and_version(self, job: Job) -> Tuple[str, str]:
        prompt = f"""
        공고를 분석하여 가장 적합한 도메인(sns, matching, commerce, logistics, fintech, search)과 버전(verA, verB)을 선택하여 응답하세요.

        [주의 사항]
        - 마크다운이나 다른 설명 없이 오직 단일 JSON 객체 형식만 출력해야 합니다.

        공고: {job.company} - {job.title} / {job.detail_text[:300]}
        응답 포맷 예시: {{"domain": "commerce", "version": "verA"}}
        """
        try:
            res_text = self._call_api_with_retry(prompt)
            cleaned_text = self._clean_json_text(res_text)
            data = json.loads(cleaned_text)
            return data.get('domain', 'commerce'), data.get('version', 'verA')
        except Exception as e:
            print(f"[LLM] domain/version 선택 중 예외: {e}")
            return 'commerce', 'verA'

    def evaluate_and_customize(self, job: Job, resume_text: str, cover_text: str) -> JobEvaluation:
        eval_prompt = f"""
        당신은 지원자의 합격을 돕는 IT 백엔드 커리어 코치입니다.

        [채용 공고]
        구직 사이트(플랫폼): {job.platform}
        회사명: {job.company} / 직무: {job.title}
        근무위치: {job.location} / 요구경력: {job.required_experience}
        상세 내용: {job.detail_text}

        [지원자 이력서 Master Data & 구직 사이트별 규격 서식]
        {resume_text}

        [공통 자소서 작성 규칙 & 선택된 원본 자소서]
        {cover_text}

        ======================================================================
        🚨 [최우선 절대 원칙] 🚨
        1. [플랫폼 규격 완전 반영 (핵심)]: 
           - '{resume_text}' 본문에 포함된 **[{job.platform}]** 전용 서식 항목(목차, 구성)을 그대로 가져와서 그 구조에 맞추어 지원자의 이력서 내용을 요약 및 재구성하세요.
           - 절대로 공통 서식이나 임의의 템플릿으로 작성하지 마시고, 반드시 해당 구직 사이트({job.platform}) 특유의 이력서 작성 양식을 준수하세요.
        2. [허위 작성 절대 금지]: 지원자의 이력서/자소서에 없는 스택(예: Python, Go, Node.js 등)이나 거짓 성과를 절대 추가하지 마세요.
        3. [자소서 항목별 글자 수 필수 충족]:
           - 1. 지원동기 및 입사 후 포부: 공백 포함 반드시 900자 ~ 980자 사이 작성
           - 2. 직무 역량이 드러나는 경험 ①: 공백 포함 반드시 1,300자 ~ 1,450자 사이 작성
           - 3. 직무 역량이 드러나는 경험 ②: 공백 포함 반드시 1,300자 ~ 1,450자 사이 작성
           - 4. 저의 개발 철학과 성장 방식: 공백 포함 반드시 1,300자 ~ 1,450자 사이 작성
        4. [마킹 및 치환 규칙]:
           - 추가/강조된 핵심 표현: **내용** (볼드체)
           - 삭제/수정된 기존 표현: ~~내용~~ (취소선)
           - '[회사명]' 단어는 '{job.company}'(으로/로) 정확히 치환하여 작성하세요.
        ======================================================================

        [수행 작업]
        1. 적합도('상', '중', '하') 및 분석 의견 도출
        2. 공고와 일치하는 주요 기술 스택 리스트 구성
        3. 해당 구직 사이트({job.platform}) 규격을 반영한 이력서 요약 Markdown 구성
        4. 4개 항목 및 글자 수 조건(1번: 900~980자, 2~4번: 1300~1450자)을 엄밀히 지킨 자소서 완성본 Markdown 구성
        """
        try:
            # config에 EvaluationSchema를 전달하고 _call_api_with_retry 사용
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationSchema
            )
            res_text = self._call_api_with_retry(eval_prompt, config=config)

            cleaned_text = self._clean_json_text(res_text)
            res_json = self._safe_parse_json(cleaned_text)

            return JobEvaluation(
                job=job,
                score=res_json.get('score', '하'),
                match_or_lack_reason=res_json.get('match_or_lack_reason', ''),
                matching_tech_stacks=res_json.get('matching_tech_stacks', []),
                customized_resume_summary_html=res_json.get('customized_resume_summary_html', ''),
                customized_cover_letter_html=res_json.get('customized_cover_letter_html', '')
            )
        except Exception as e:
            raise RuntimeError(f"Gemini 평가 중 오류 발생: {e}")