import streamlit as st
import arxiv
import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import qrcode

# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="Paper to Poster Pro", layout="wide", initial_sidebar_state="auto")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 32)
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 24)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 20)
        return font_b, font_rl, font_rs
    except IOError:
        st.warning(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다. 기본 폰트로 대체됩니다.")
        default_font = ImageFont.load_default()
        return default_font, default_font, default_font

font_bold_file = "NotoSansKR-Bold.otf"
font_bold, font_regular_large, font_regular_small = load_font(font_bold_file)


# --- 핵심 기능 함수들 ---

# ==============================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 신규: 이미지 추출 기능 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# ==============================================================================
def extract_key_image_from_pdf(pdf_stream):
    """PDF에서 가장 큰 이미지를 추출하여 PIL 이미지 객체로 반환합니다."""
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        max_image_area = 0
        best_image = None

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                # 이미지의 면적 계산 (단순히 너비*높이)
                image_area = base_image["width"] * base_image["height"]

                # 가장 큰 면적의 이미지를 저장
                if image_area > max_image_area:
                    max_image_area = image_area
                    best_image = Image.open(BytesIO(image_bytes))
        
        return best_image
    except Exception as e:
        st.warning(f"PDF에서 이미지 추출 중 오류 발생: {e}")
        return None

def get_paper_from_arxiv(arxiv_id):
    try:
        paper = next(arxiv.Search(id_list=[arxiv_id]).results())
        return paper
    except Exception: return None

def summarize_text_with_gpt(client, text, section):
    if not text.strip(): return f"[{section} 섹션의 내용을 찾지 못했습니다.]"
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes academic papers in Korean."},
                {"role": "user", "content": f"다음 {section}을 한국어 3문장으로 요약해줘:\n\n{text}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"{section} 요약 중 OpenAI API 오류 발생: {e}")
        return f"[{section} 요약 실패]"

def find_section_text(full_text, section_name):
    start_index = full_text.lower().find(section_name.lower())
    if start_index == -1: return ""
    next_sections = ["method", "result", "conclusion", "discussion", "reference"]
    end_index = len(full_text)
    temp_start = start_index + len(section_name)
    for next_sec in next_sections:
        if next_sec.lower() != section_name.lower():
            next_sec_index = full_text.lower().find(next_sec.lower(), temp_start)
            if next_sec_index != -1:
                end_index = min(end_index, next_sec_index)
    return full_text[start_index:end_index]


# ==============================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 수정: 포스터 생성 함수 (이미지 추가) ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# ==============================================================================
def create_poster_pro(title, authors, summaries, key_image=None, arxiv_link=None):
    """이미지까지 포함하는 최종 포스터 생성 함수"""
    width, height = 900, 1600 # 세로 길이 확장
    bg_color = "#FFFFFF"
    header_color = "#F0F2F6"
    title_color = "#0E1117"
    text_color = "#31333F"
    accent_color = "#4A6CFA"
    
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    
    def draw_multiline_text(position, text, font, max_width, fill):
        # ... (이전과 동일한 헬퍼 함수)
        x, y = position
        lines = []
        words = text.split()
        if not words: return y
        line = ""
        for word in words:
            if d.textlength(line + word + " ", font=font) <= max_width:
                line += word + " "
            else:
                lines.append(line)
                line = word + " "
        lines.append(line)
        for line in lines:
            d.text((x, y), line, font=font, fill=fill)
            y += font.getbbox("A")[3] + 8
        return y

    # --- 헤더 ---
    d.rectangle([(0, 0), (width, 150)], fill=header_color)
    current_y = draw_multiline_text((40, 40), title, font_bold, 720, title_color)
    author_text = ", ".join(authors)
    draw_multiline_text((40, current_y), author_text, font_regular_small, 720, text_color)
    if arxiv_link:
        qr_img = qrcode.make(arxiv_link).resize((100, 100))
        img.paste(qr_img, (width - 140, 25))
    
    current_y = 180
    
    # --- Introduction 섹션 ---
    if "Introduction" in summaries:
        d.rectangle([(40, current_y), (width - 40, current_y + 40)], fill=accent_color)
        d.text((60, current_y + 6), "Introduction", font=font_regular_large, fill=bg_color)
        current_y += 55
        current_y = draw_multiline_text((40, current_y), summaries["Introduction"], font_regular_small, 820, text_color)
        current_y += 40

    # --- 핵심 이미지 배치 ---
    if key_image:
        key_image.thumbnail((width - 80, 400)) # 이미지 최대 크기 조절
        img_x = (width - key_image.width) // 2
        img_y = current_y
        img.paste(key_image, (img_x, img_y))
        current_y += key_image.height + 40

    # --- Methodology & Results 섹션 ---
    for section_title in ["Methodology", "Results"]:
        if section_title in summaries:
            d.rectangle([(40, current_y), (width - 40, current_y + 40)], fill=accent_color)
            d.text((60, current_y + 6), section_title, font=font_regular_large, fill=bg_color)
            current_y += 55
            current_y = draw_multiline_text((40, current_y), summaries[section_title], font_regular_small, 820, text_color)
            current_y += 40

    return img

# --- Streamlit App UI ---
st.title("📄➡️🖼️ Paper to Poster Pro")
st.markdown("논문(arXiv ID 또는 PDF)을 입력하면 AI가 **텍스트를 요약**하고 **핵심 이미지를 추출**하여 포스터로 만듭니다.")

with st.sidebar:
    st.header("⚙️ 설정")
    try:
        openai_api_key = st.secrets["OPENAI_API_KEY"]
        st.info("배포자의 API 키로 앱이 운영됩니다.")
    except:
        st.error("API 키를 찾을 수 없습니다.")
        openai_api_key = None
    input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

# --- 메인 로직 ---
pdf_stream = None
if input_option == 'arXiv ID':
    arxiv_id_input = st.text_input("2. 논문의 arXiv ID를 입력하세요", "1710.06945") # CycleGAN 예시
    if arxiv_id_input:
        with st.spinner('arXiv에서 논문 정보를 가져오는 중...'):
            paper_info = get_paper_from_arxiv(arxiv_id_input)
        if paper_info:
            response = requests.get(paper_info.pdf_url)
            pdf_stream = BytesIO(response.content)
            st.success(f"**{paper_info.title}** 논문 로드 완료!")
else:
    uploaded_file = st.file_uploader("2. 논문 PDF 파일을 업로드하세요", type="pdf")
    if uploaded_file:
        paper_info = {"title": uploaded_file.name.replace(".pdf", ""), "authors": ["Uploaded PDF"]}
        pdf_stream = BytesIO(uploaded_file.getvalue())
        st.success("PDF 파일 업로드 완료!")

if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not pdf_stream or not openai_api_key)):
    client = OpenAI(api_key=openai_api_key)
    
    # 1. 텍스트 추출 및 요약
    with st.spinner("AI가 논문을 읽고 요약하는 중..."):
        pdf_stream.seek(0)
        full_text = "".join(page.get_text() for page in fitz.open(stream=pdf_stream, filetype="pdf"))
        summaries = {}
        for section in ["Introduction", "Methodology", "Results"]:
            text = find_section_text(full_text, section)
            summaries[section] = summarize_text_with_gpt(client, text[:4000], section)
    st.success("텍스트 요약 완료!")

    # 2. 이미지 추출
    with st.spinner("논문에서 핵심 이미지를 추출하는 중..."):
        key_image = extract_key_image_from_pdf(pdf_stream)
        if key_image:
            st.success("핵심 이미지 추출 완료!")
        else:
            st.warning("논문에서 이미지를 찾지 못했습니다.")

    # 3. 포스터 생성
    with st.spinner("요약된 텍스트와 이미지로 포스터를 생성합니다..."):
        title = paper_info.title if hasattr(paper_info, 'title') else paper_info.get('title', '제목 없음')
        authors = [str(author) for author in paper_info.authors] if hasattr(paper_info, 'authors') else paper_info.get('authors', [])
        arxiv_link = paper_info.entry_id if hasattr(paper_info, 'entry_id') else None
        
        poster_image = create_poster_pro(title, authors, summaries, key_image, arxiv_link)
        st.success("🎉 포스터 생성 완료!")
        st.image(poster_image, caption="생성된 포스터", use_container_width=True)

        img_byte_arr = BytesIO()
        poster_image.save(img_byte_arr, format='PNG')
        st.download_button("📥 포스터 다운로드 (PNG)", img_byte_arr.getvalue(), f"poster_{arxiv_id_input if 'arxiv_id_input' in locals() else 'uploaded'}.png", "image/png")

else:
    st.info("API 키를 확인하고 논문을 입력한 후 '포스터 생성하기' 버튼을 누르세요.")