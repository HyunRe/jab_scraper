from pathlib import Path
import pdfplumber

def convert_pdf_to_txt():
    # 현재 실행 중인 .py 파일의 위치 기준으로 프로젝트 루트 및 documents/assets 경로 설정
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / "documents"
    output_path = base_dir / "assets"

    # 폴더가 없으면 자동 생성
    input_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    # documents 폴더 내 모든 PDF 파일 탐색
    pdf_files = list(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"⚠️ '{input_path}' 폴더에 PDF 파일이 없습니다.")
        return

    print(f"🚀 총 {len(pdf_files)}개의 PDF 파일 변환을 시작합니다...\n")

    for pdf_file in pdf_files:
        txt_file = output_path / f"{pdf_file.stem}.txt"

        try:
            with pdfplumber.open(pdf_file) as pdf:
                full_text = []
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        full_text.append(f"--- Page {i+1} ---\n{text}\n")

                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(full_text))

            print(f"✅ 변환 완료: {pdf_file.name} -> {txt_file.name}")
        except Exception as e:
            print(f"❌ 변환 실패 ({pdf_file.name}): {e}")

if __name__ == "__main__":
    convert_pdf_to_txt()