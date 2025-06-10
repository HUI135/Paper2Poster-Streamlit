import streamlit as st
import arxiv
import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from io import BytesIO
import qrcode
import re

# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="PosterGenius Assistant", layout="wide", initial_sidebar_state="auto")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 32)
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 24)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 20)
        return font_b, font_rl, font_rs
    except IOError:
        st.error(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다. 앱 작동에 필수적입니다.")
        return None, None, None

font_bold, font_regular_large, font_regular_small = load_font("NotoSansKR-Bold.otf")


# --- 핵심 기능 함수들 ---

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: 모든 이미지 추출 기능 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def extract_all_images_from_pdf(pdf_stream):
    """PDF에서 의미있는 크기의 모든 이미지를 추출하여 리스트로 반환합니다."""
    images = []
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                
                # 너무 작은 이미지는 제외 (예: 아이콘, 구분선 등)
                if base_image["width"] < 100 or base_image["height"] < 100:
                    continue

                image_bytes = base_image["image"]
                pil_image = Image.open(BytesIO(image_bytes))

                # 이미지 모드를 RGB로 통일하고, 좌우 반전 문제 해결
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")
                
                # 일부 PDF에서 이미지가 좌우 반전되는 현상을 교정
                corrected_image = ImageOps.mirror(pil_image)
                images.append(corrected_image)
                
        return images
    except Exception as e:
        st.warning(f"PDF에서 이미지 추출 중 오류 발생: {e}")
        return []

# (다른 함수들은 이전과 거의 동일)
def find_section_text(full_text, section_keywords):
    full_text_lower = full_text.lower()
    for keyword in section_keywords:
        try:
            match = re.search(r"^(?:\d+\.?\s*)?" + re.escape(keyword) + r"\s*$", full_text_lower, re.MULTILINE | re.IGNORECASE)
            if match:
                start_index = match.start()
                next_section_keywords = ["introduction", "method", "result", "conclusion", "discussion", "reference"]
                end_index = len(full_text)
                temp_start = match.end()
                for next_kw in next_section_keywords:
                    if next_kw not in keyword:
                        next_match = re.search(r"^(?:\d+\.?\s*)?" + re.escape(next_kw), full_text_lower[temp_start:], re.MULTILINE | re.IGNORECASE)
                        if next_match:
                            end_index = min(end_index, temp_start + next_match.start())
                return full_text[start_index:end_index]
        except Exception:
            continue
    return ""

def get_paper_from_arxiv(arxiv_id):
    try:
        return next(arxiv.Search(id_list=[arxiv_id]).results())
    except Exception: return None

def summarize_text_with_gpt(client, text, section_name):
    if not text.strip(): return f"[{section_name} 섹션의 내용을 찾지 못했습니다.]"
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant that summarizes academic papers in Korean."},
                      {"role": "user", "content": f"다음 {section_name}을 한국어 3문장으로 요약해줘:\n\n{text}"}]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"{section_name} 요약 중 OpenAI API 오류 발생: {e}")
        return f"[{section_name} 요약 실패]"

def create_poster_pro(title, authors, summaries, key_image=None, arxiv_link=None):
    width, height = 900, 1600
    img = Image.new('RGB', (width, height), color="#FFFFFF")
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
                lines.append(line); line = word + " "
        lines.append(line)
        for line in lines:
            d.text((x, y), line, font=font, fill=fill)
            y += font.getbbox("A")[3] + 8
        return y
    d.rectangle([(0, 0), (width, 150)], fill="#F0F2F6")
    current_y = draw_multiline_text((40, 40), title, font_bold, 720, "#0E1117")
    author_text = ", ".join(authors)
    draw_multiline_text((40, current_y), author_text, font_regular_small, 720, "#31333F")
    if arxiv_link:
        qr_img = qrcode.make(arxiv_link).resize((100, 100))
        img.paste(qr_img, (width - 140, 25))
    current_y = 180
    if "Introduction" in summaries:
        d.rectangle([(40, current_y), (width - 40, current_y + 40)], fill="#4A6CFA")
        d.text((60, current_y + 6), "Introduction", font=font_regular_large, fill="#FFFFFF")
        current_y += 55
        current_y = draw_multiline_text((40, current_y), summaries["Introduction"], font_regular_small, 820, "#31333F")
        current_y += 40
    if key_image:
        key_image.thumbnail((width - 80, 400))
        img_x = (width - key_image.width) // 2
        img.paste(key_image, (img_x, current_y))
        current_y += key_image.height + 40
    for section_title in ["Methodology", "Results"]:
        if section_title in summaries:
            d.rectangle([(40, current_y), (width - 40, current_y + 40)], fill="#4A6CFA")
            d.text((60, current_y + 6), section_title, font=font_regular_large, fill="#FFFFFF")
            current_y += 55
            current_y = draw_multiline_text((40, current_y), summaries[section_title], font_regular_small, 820, "#31333F")
            current_y += 40
    return img


# --- Streamlit App UI ---
if not all([font_bold, font_regular_large, font_regular_small]):
    st.error("폰트 파일 로딩에 실패하여 앱을 실행할 수 없습니다. 폰트 파일을 확인해주세요.")
else:
    st.title("📄➡️🖼️ PosterGenius Assistant (v4)")
    st.markdown("AI가 논문을 분석하여 텍스트 요약과 이미지 옵션을 제공하면, 사용자가 직접 콘텐츠를 선택하여 포스터 초안을 완성합니다.")

    with st.sidebar:
        st.header("⚙️ 설정")
        try:
            openai_api_key = st.secrets["OPENAI_API_KEY"]
            st.info("배포자의 API 키로 앱이 운영됩니다.")
        except:
            st.error("API 키를 찾을 수 없습니다."); openai_api_key = None
        input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

    pdf_stream, paper_info = None, None
    if input_option == 'arXiv ID':
        arxiv_id_input = st.text_input("2. 논문의 arXiv ID를 입력하세요", "1703.06868")
        if arxiv_id_input:
            with st.spinner('arXiv에서 논문 정보를 가져오는 중...'): paper_info = get_paper_from_arxiv(arxiv_id_input)
            if paper_info:
                response = requests.get(paper_info.pdf_url); pdf_stream = BytesIO(response.content)
                st.success(f"**{paper_info.title}** 논문 로드 완료!")
    else:
        uploaded_file = st.file_uploader("2. 논문 PDF 파일을 업로드하세요", type="pdf")
        if uploaded_file:
            paper_info = {"title": uploaded_file.name.replace(".pdf", ""), "authors": ["Uploaded PDF"]}
            pdf_stream = BytesIO(uploaded_file.getvalue())

    if pdf_stream:
        st.markdown("---")
        st.subheader("3. 포스터에 포함할 이미지 선택")
        
        extracted_images = extract_all_images_from_pdf(pdf_stream)
        
        if not extracted_images:
            st.warning("논문에서 추출할 만한 이미지를 찾지 못했습니다.")
            selected_image_index = -1
        else:
            # st.radio를 사용해 사용자가 이미지를 선택하게 함
            options = [f"Image {i+1}" for i in range(len(extracted_images))] + ["이미지 선택 안함"]
            selected_option = st.radio("아래 썸네일 중 마음에 드는 이미지를 하나 고르세요.", options, horizontal=True)

            # 썸네일 표시
            cols = st.columns(len(extracted_images))
            for i, image in enumerate(extracted_images):
                with cols[i]:
                    st.image(image, caption=f"Image {i+1}", use_column_width=True)
            
            if selected_option != "이미지 선택 안함":
                selected_image_index = int(selected_option.split(" ")[1]) - 1
            else:
                selected_image_index = -1

        st.markdown("---")
        if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not openai_api_key)):
            final_image = extracted_images[selected_image_index] if selected_image_index != -1 else None

            client = OpenAI(api_key=openai_api_key)
            with st.spinner("AI가 텍스트를 요약하는 중..."):
                pdf_stream.seek(0)
                full_text = "".join(page.get_text() for page in fitz.open(stream=pdf_stream, filetype="pdf"))
                summaries = {}
                sections = {"Introduction": ["introduction"], "Methodology": ["methodology", "methods"], "Results": ["results", "experiments"]}
                for name, kws in sections.items():
                    text = find_section_text(full_text, kws)
                    summaries[name] = summarize_text_with_gpt(client, text[:4000], name)
            st.success("텍스트 요약 완료!")
            
            with st.spinner("포스터를 생성합니다..."):
                title = paper_info.get('title', '제목 없음') if isinstance(paper_info, dict) else getattr(paper_info, 'title', '제목 없음')
                authors = paper_info.get('authors', []) if isinstance(paper_info, dict) else [str(a) for a in getattr(paper_info, 'authors', [])]
                arxiv_link = getattr(paper_info, 'entry_id', None)
                
                poster_image = create_poster_pro(title, authors, summaries, final_image, arxiv_link)
                st.success("🎉 포스터 생성 완료!")
                st.image(poster_image, caption="생성된 포스터", use_container_width=True)

                img_byte_arr = BytesIO(); poster_image.save(img_byte_arr, format='PNG')
                st.download_button("📥 포스터 다운로드 (PNG)", img_byte_arr.getvalue(), f"poster.png", "image/png")