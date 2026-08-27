import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List
from datetime import datetime
from app.domain.models import Job, JobEvaluation


class EmailNotifier:
    def __init__(self, gmail_user: str, gmail_pass: str, to_email: str):
        self.gmail_user = gmail_user
        self.gmail_pass = gmail_pass
        self.to_email = to_email
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465

    def send_daily_raw_report(self, jobs: List[Job]):
        """수집된 raw 공고 목록(List[Job]) 발송 리포트"""
        if not jobs:
            print("[Email] 전송할 신규 수집 공고가 없습니다.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[수집 리포트] {today_str} 신규 채용 공고 ({len(jobs)}건)"

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;">
                📢 {today_str} 신규 공고 수집 리포트
            </h2>
            <p>오늘 수집된 총 <b>{len(jobs)}건</b>의 신규 공고입니다. 상세 분석은 노션 DB에서 '분석' 상태를 '요청'으로 변경해 주세요.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <ul>
        """
        for job in jobs:
            html_content += f"""
            <li style="margin-bottom: 10px;">
                <b>[{job.company}]</b> <a href="{job.url}" target="_blank">{job.title}</a> ({job.location or "위치 미상"} / {job.required_experience or "경력 무관"})
            </li>
            """
        html_content += """
            </ul>
        </body>
        </html>
        """

        self._send_email(subject, html_content)

    def send_daily_report(self, evaluations: List[JobEvaluation]):
        """LLM 2단계 평가 완료된 목록(List[JobEvaluation]) 발송 리포트"""
        if not evaluations:
            print("[Email] 전송할 추천 공고가 없습니다.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        subject = f"[채용 리포트] {today_str} 추천 채용 공고 ({len(evaluations)}건)"

        score_colors = {
            "상": "#2e7d32",
            "중": "#f57c00",
            "하": "#d32f2f"
        }

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;">
                📢 {today_str} 일일 맞춤 채용 리포트
            </h2>
            <p>오늘 수집 및 분석된 총 <b>{len(evaluations)}건</b>의 추천 공고입니다.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        """

        for eval_item in evaluations:
            badge_color = score_colors.get(eval_item.score, "#757575")
            title_text = f"[{eval_item.job.company}] {eval_item.job.title}"
            notion_url = getattr(eval_item, "notion_url", None)

            notion_btn_html = ""
            if notion_url:
                notion_btn_html = f"""
                    <a href="{notion_url}" target="_blank" style="display: inline-block; background-color: #2f3437; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: bold; margin-left: 8px;">
                        📝 노션 리포트 바로가기
                    </a>
                """

            html_content += f"""
            <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 25px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 18px;">
                        <a href="{eval_item.job.url}" target="_blank" style="color: #1a73e8; text-decoration: none;">
                            {title_text}
                        </a>
                    </h3>
                    <span style="background-color: {badge_color}; color: #ffffff; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 13px;">
                        적합도: {eval_item.score}
                    </span>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px; font-size: 14px; background-color: #f8f9fa; border-radius: 6px; padding: 10px;">
                    <tr>
                        <td style="padding: 6px 12px; width: 15%; font-weight: bold; color: #555;">🏢 회사명</td>
                        <td style="padding: 6px 12px; width: 35%;">{eval_item.job.company}</td>
                        <td style="padding: 6px 12px; width: 15%; font-weight: bold; color: #555;">📍 근무위치</td>
                        <td style="padding: 6px 12px; width: 35%;">{eval_item.job.location or "정보 없음"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 12px; font-weight: bold; color: #555;">💼 요구경력</td>
                        <td style="padding: 6px 12px;">{eval_item.job.required_experience or "무관"}</td>
                        <td style="padding: 6px 12px; font-weight: bold; color: #555;">⏰ 마감일</td>
                        <td style="padding: 6px 12px;">{eval_item.job.deadline or "상시 채용"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 12px; font-weight: bold; color: #555;">🌐 도메인</td>
                        <td style="padding: 6px 12px;">{eval_item.matched_domain}</td>
                        <td style="padding: 6px 12px; font-weight: bold; color: #555;">📅 수집일자</td>
                        <td style="padding: 6px 12px;">{today_str}</td>
                    </tr>
                </table>
                <div style="border-top: 1px dashed #ddd; padding-top: 12px; margin-top: 10px;">
                    <p style="margin: 5px 0;"><b>📌 적합성 판단 및 분석:</b> {eval_item.match_or_lack_reason}</p>
                    <p style="margin: 5px 0;"><b>🛠 매칭 기술 스택:</b> {", ".join(eval_item.matching_tech_stacks)}</p>
                </div>
                <div style="margin-top: 15px; text-align: right;">
                    <a href="{eval_item.job.url}" target="_blank" style="display: inline-block; background-color: #1a73e8; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: bold;">
                        🔗 공고 링크 바로가기
                    </a>
                    {notion_btn_html}
                </div>
            </div>
            """

        html_content += """
            <p style="font-size: 12px; color: #888; text-align: center; margin-top: 30px;">
                본 이메일은 노션 데이터베이스와 연동된 자동화 시스템에서 발송되었습니다.
            </p>
        </body>
        </html>
        """

        self._send_email(subject, html_content)

    def _send_email(self, subject: str, html_content: str):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.gmail_user
        msg["To"] = self.to_email
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.gmail_user, self.gmail_pass)
                server.sendmail(self.gmail_user, self.to_email, msg.as_string())
            print(f"[Email] '{subject}' 이메일 리포트 발송 완료")
        except Exception as e:
            print(f"[Email] 이메일 발송 중 오류 발생: {e}")