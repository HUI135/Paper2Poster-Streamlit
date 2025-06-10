import streamlit as st
import arxiv
import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import qrcode # QR 코드 생성을 위해 추가

# --- Streamlit 페이지 설정 (가장 먼저 실행되어야 함) ---
st.set_page_config(page_title="Paper to Poster", layout="wide", initial_sidebar_state="auto")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        # 폰트 사이즈를 튜플 대신 개별적으로 반환하도록 수정
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

def get_paper_from_arxiv(arxiv_id):
    try:
        paper = next(arxiv.Search(id_list=[arxiv_id]).results())
        return paper
    except Exception as e:
        st.error(f"arXiv에서 논문을 찾는 중 오류가 발생했습니다: {e}")
        return None

def extract_text_from_pdf(pdf_file):
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    return "".join(page.get_text() for page in doc)

def summarize_text_with_gpt(client, text, section):
    if not text.strip():
        return f"[{section} 섹션의 내용을 찾지 못해 요약할 수 없습니다.]"
    
    prompt_dict = {
        "Introduction": "다음 서론을 한국어로 2-3문장으로 요약해줘:",
        "Methodology": "다음 방법론을 핵심 아이디어 위주로 한국어로 2-3문장으로 요약해줘:",
        "Results": "다음 결과 섹션을 중요한 발견점 위주로 한국어로 2-3문장으로 요약해줘:"
    }
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes academic papers in Korean."},
                {"role": "user", "content": f"{prompt_dict[section]}\n\n{text}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        # OpenAI API 오류를 st.error로 바로 표시하고, 요약 실패 메시지를 반환
        st.error(f"{section} 요약 중 OpenAI API 오류 발생: {e}")
        return f"[{section} 요약 실패: API 오류 발생]"

def find_section_text(full_text, section_name):
    start_index = full_text.lower().find(section_name.lower())
    if start_index == -1: return ""
    next_sections = ["method", "result", "conclusion", "discussion", "reference"]
    end_index = len(full_text)
    temp_start = start_index + len(section_name)
    for next_sec in next_sections:
        if next_sec.lower() not in section_name.lower():
             next_sec_index = full_text.lower().find(next_sec.lower(), temp_start)
             if next_sec_index != -1:
                 end_index = min(end_index, next_sec_index)
    return full_text[start_index:end_index]

# ==============================================================================
# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 이 함수가 실제 포스터 디자인을 만듭니다 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
# ==============================================================================
def create_poster_v2(title, authors, summaries, arxiv_link=None):
    """개선된 디자인의 포스터 생성 함수"""
    width, height = 900, 1400
    bg_color = "#FFFFFF"
    header_color = "#F0F2F6"
    title_color = "#0E1117"
    text_color = "#31333F"
    accent_color = "#4A6CFA"
    
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    
    def draw_multiline_text(position, text, font, max_width, fill):
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

    d.rectangle([(0, 0), (width, 150)], fill=header_color)
    current_y = draw_multiline_text((40, 40), title, font_bold, 820, title_color)
    author_text = ", ".join(authors)
    draw_multiline_text((40, current_y), author_text, font_regular_small, 820, text_color)

    if arxiv_link:
        qr_img = qrcode.make(arxiv_link)
        qr_img = qr_img.resize((100, 100))
        img.paste(qr_img, (width - 140, 25))

    current_y = 180
    
    for section_title, content in summaries.items():
        d.rectangle([(40, current_y), (width - 40, current_y + 40)], fill=accent_color)
        d.text((60, current_y + 6), section_title, font=font_regular_large, fill=bg_color)
        current_y += 55
        
        current_y = draw_multiline_text((40, current_y), content, font_regular_small, 820, text_color)
        current_y += 40

    return img
# ==============================================================================
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
# ==============================================================================


# --- Streamlit App UI ---
st.title("📄➡️🖼️ Paper to Poster Generator v2")
st.markdown("논문(arXiv ID 또는 PDF)을 입력하면 AI가 핵심 내용을 요약하여 **디자인이 개선된 포스터**로 만들어 드립니다.")

with st.sidebar:
    st.header("⚙️ 설정")
    # secrets에서 API 키를 직접 불러오도록 수정
    try:
        openai_api_key = st.secrets["OPENAI_API_KEY"]
        st.info("배포자의 API 키로 앱이 운영됩니다.")
    except:
        st.error("API 키를 찾을 수 없습니다. Streamlit secrets에 OPENAI_API_KEY를 설정해주세요.")
        openai_api_key = None
        
    input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

# 메인 화면
paper_info = None
full_text = ""
arxiv_id = None

if input_option == 'arXiv ID':
    arxiv_id_input = st.text_input("2. 논문의 arXiv ID를 입력하세요", "2305.12983")
    if arxiv_id_input:
        arxiv_id = arxiv_id_input
        paper_info = get_paper_from_arxiv(arxiv_id)
        if paper_info:
            try:
                with st.spinner('논문 PDF를 다운로드하고 텍스트를 추출하는 중...'):
                    response = requests.get(paper_info.pdf_url)
                    response.raise_for_status()
                    pdf_file = BytesIO(response.content)
                    full_text = extract_text_from_pdf(pdf_file)
                    st.success(f"**{paper_info.title}** 논문 텍스트 추출 완료!")
            except Exception as e:
                st.error(f"PDF 처리 중 오류 발생: {e}")
                paper_info = None
else:
    uploaded_file = st.file_uploader("2. 논문 PDF 파일을 업로드하세요", type="pdf")
    if uploaded_file is not None:
        with st.spinner('PDF 텍스트를 추출하는 중입니다...'):
            full_text = extract_text_from_pdf(uploaded_file)
            st.success("PDF 텍스트 추출 완료!")
            paper_info = {"title": uploaded_file.name.replace(".pdf", ""), "authors": ["Uploaded PDF"]}

if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not full_text or not openai_api_key)):
    client = OpenAI(api_key=openai_api_key)
    summaries = {}
    
    with st.spinner("AI가 논문을 읽고 요약하는 중입니다... (1-2분 소요)"):
        sections_to_summarize = {
            "Introduction": find_section_text(full_text, "introduction"),
            "Methodology": find_section_text(full_text, "method"),
            "Results": find_section_text(full_text, "result")
        }
        for section, text in sections_to_summarize.items():
            summaries[section] = summarize_text_with_gpt(client, text[:4000], section)
    st.success("논문 요약 완료!")

    with st.spinner("포스터 이미지를 생성하는 중입니다..."):
        title = paper_info.title if hasattr(paper_info, 'title') else paper_info.get('title', '제목 없음')
        authors = [str(author) for author in paper_info.authors] if hasattr(paper_info, 'authors') else paper_info.get('authors', [])
        arxiv_link = paper_info.entry_id if hasattr(paper_info, 'entry_id') else None
        
        # ▼▼▼▼▼▼▼▼▼▼▼ 여기서 개선된 v2 함수를 호출합니다 ▼▼▼▼▼▼▼▼▼▼▼
        poster_image = create_poster_v2(title, authors, summaries, arxiv_link)
        
        st.success("포스터 생성 완료!")
        st.image(poster_image, caption="생성된 포스터", use_container_width=True)

        img_byte_arr = BytesIO()
        poster_image.save(img_byte_arr, format='PNG')
        
        st.download_button(
            label="📥 포스터 다운로드 (PNG)",
            data=img_byte_arr.getvalue(),
            file_name=f"poster_{arxiv_id if arxiv_id else 'uploaded'}.png",
            mime="image/png"
        )
else:
    st.info("사이드바에서 입력 방식을 선택하고 논문을 입력한 후 '포스터 생성하기' 버튼을 누르세요.")