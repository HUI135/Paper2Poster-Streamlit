import streamlit as st
import arxiv
import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from io import BytesIO
import qrcode
import json

# --- Streamlit 페이지 설정 ---
st.set_page_config(page_title="PosterGenius Assistant v8", layout="wide")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 48)
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 28)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 20)
        font_caption = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 16)
        return font_b, font_rl, font_rs, font_caption
    except IOError:
        st.error(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다."); return (None,)*4

font_bold, font_regular_large, font_regular_small, font_caption = load_font("NotoSansKR-Bold.otf")


# --- 핵심 기능 함수 ---

def extract_images_from_pdf(pdf_stream):
    images = []
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        for page in doc:
            for img_info in page.get_images(full=True):
                if img_info[0] < 0 or img_info[2] < 150 or img_info[3] < 150: continue
                base_image = doc.extract_image(img_info[0])
                pil_image = Image.open(BytesIO(base_image["image"]))
                if pil_image.mode != "RGB": pil_image = pil_image.convert("RGB")
                images.append(pil_image)
        return images
    except Exception as e:
        st.warning(f"이미지 추출 중 오류: {e}"); return []

def extract_and_summarize(client, text):
    st.info("GPT가 논문 전체를 분석하여 섹션 추출 및 요약을 동시에 진행합니다...")
    system_prompt = "You are an expert academic assistant. Your task is to analyze an academic paper's text. First, extract the content of the 'Introduction', 'Methodology', and 'Results' sections. For 'Methodology', also accept 'Methods'. For 'Results', also accept 'Experiments'. Then, summarize each extracted section in 3-4 sentences in KOREAN. Respond ONLY with a valid JSON object. The JSON object must have keys 'introduction_summary', 'methodology_summary', and 'results_summary'. If a section is not found, its summary should be a string stating that. Do not include explanations outside the JSON."
    try:
        response = client.chat.completions.create(model="gpt-4-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text[:15000]}], response_format={"type": "json_object"})
        summaries = json.loads(response.choices[0].message.content)
        return summaries
    except Exception as e:
        st.error(f"GPT 기반 추출/요약 중 오류: {e}"); return {k: "처리 실패" for k in ["introduction_summary", "methodology_summary", "results_summary"]}

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: 3단 레이아웃 포스터 생성 함수 복원 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def create_3_column_poster(title, authors, summaries, images=[], arxiv_link=None):
    width, height = 1800, 1000
    img = Image.new('RGB', (width, height), color="#FFFFFF")
    d = ImageDraw.Draw(img)
    
    def draw_multiline_text(position, text, font, max_width, fill, spacing=10):
        x, y = position; lines = []; words = text.split()
        if not words: return y
        line = ""
        for word in words:
            if d.textlength(line + word + " ", font=font) <= max_width: line += word + " "
            else: lines.append(line); line = word + " "
        lines.append(line)
        for line in lines: d.text((x, y), line, font=font, fill=fill); y += font.getbbox("A")[3] + spacing
        return y

    d.rectangle([(0, 0), (width, 120)], fill="#F0F2F6")
    if arxiv_link:
        qr_img = qrcode.make(arxiv_link).resize((90, 90)); img.paste(qr_img, (width - 120, 15))
    draw_multiline_text((40, 30), title, font_bold, 1600, "#0E1117")
    
    margin, gap = 40, 40
    col_width = (width - 2 * margin - 2 * gap) // 3
    col1_x, col2_x, col3_x = margin, margin + col_width + gap, margin + 2 * (col_width + gap)
    current_y = [150] * 3

    def draw_section(col_index, title, content):
        col_x = [col1_x, col2_x, col3_x][col_index]
        y = current_y[col_index]
        y = draw_multiline_text((col_x, y), title, font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col_x, y), (col_x + col_width, y)], fill="#DDDDDD", width=2)
        y += 15
        y = draw_multiline_text((col_x, y), content, font_regular_small, col_width, "#31333F")
        current_y[col_index] = y + 30

    if "introduction_summary" in summaries: draw_section(0, "Introduction", summaries["introduction_summary"])
    if "methodology_summary" in summaries: draw_section(0, "Methodology", summaries["methodology_summary"])
    if "results_summary" in summaries: draw_section(1, "Results", summaries["results_summary"])

    if images:
        y = current_y[2]
        y = draw_multiline_text((col3_x, y), "Figures & Tables", font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col3_x, y), (col3_x + col_width, y)], fill="#DDDDDD", width=2)
        y += 15
        for i, key_image in enumerate(images):
            key_image.thumbnail((col_width, col_width))
            img.paste(key_image, (col3_x, y))
            y += key_image.height + 5
            draw_multiline_text((col3_x, y), f"[Fig. {i+1}]", font_caption, col_width, "#888888")
            y += 25
        current_y[2] = y
    return img

# --- Streamlit App UI ---
if font_bold:
    st.title("📄➡️🖼️ PosterGenius Assistant (v8)")
    st.markdown("AI가 논문을 분석/요약하고, 사용자가 **여러 이미지를 선택**하면 **3단 가로형 포스터**를 생성합니다.")

    with st.sidebar:
        st.header("⚙️ 설정"); openai_api_key = st.secrets.get("OPENAI_API_KEY")
        if not openai_api_key: st.error("API 키를 찾을 수 없습니다.")
        input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

    pdf_stream, paper_info = None, None
    if input_option == 'arXiv ID':
        arxiv_id_input = st.text_input("2. 논문 arXiv ID 입력", "2005.12872")
        if arxiv_id_input:
            try:
                paper_info = arxiv.Search(id_list=[arxiv_id_input]).results().__next__()
                if paper_info:
                    with st.spinner('논문 PDF 다운로드 중...'): pdf_stream = BytesIO(requests.get(paper_info.pdf_url).content)
                    st.success(f"**{paper_info.title}** 로드 완료!")
            except StopIteration: st.error("해당 ID의 논문을 찾을 수 없습니다.")
    else:
        uploaded_file = st.file_uploader("2. 논문 PDF 업로드", type="pdf")
        if uploaded_file:
            paper_info = {"title": uploaded_file.name.replace(".pdf", "")}; pdf_stream = BytesIO(uploaded_file.getvalue())

    # --- 이미지 선택 로직 초기화 ---
    if 'selected_images' not in st.session_state:
        st.session_state.selected_images = []

    if pdf_stream:
        st.markdown("---")
        st.subheader("3. 포스터에 포함할 이미지 선택")
        extracted_images = extract_images_from_pdf(pdf_stream)
        
        if extracted_images:
            # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: 새로운 이미지 선택 UI ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
            st.info("포스터에 포함할 올바른 방향의 이미지를 클릭하여 선택하세요. 다중 선택이 가능합니다.")
            
            # 선택된 이미지를 관리하기 위한 로직
            if 'chosen_indices' not in st.session_state: st.session_state.chosen_indices = []
            
            num_images = len(extracted_images)
            cols = st.columns(num_images) # 요청대로 가로로 나열
            
            for i, image in enumerate(extracted_images):
                with cols[i]:
                    st.write(f"**이미지 {i+1}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.image(image, caption="원본", use_container_width=True)
                        if st.button(f"이 이미지 선택##{i}_orig", use_container_width=True):
                            if (i, "orig") not in st.session_state.chosen_indices:
                                st.session_state.chosen_indices.append((i, "orig"))
                            else:
                                st.session_state.chosen_indices.remove((i, "orig"))
                    with col2:
                        flipped_image = ImageOps.mirror(image)
                        st.image(flipped_image, caption="좌우반전", use_container_width=True)
                        if st.button(f"이 이미지 선택##{i}_flip", use_container_width=True):
                            if (i, "flip") not in st.session_state.chosen_indices:
                                st.session_state.chosen_indices.append((i, "flip"))
                            else:
                                st.session_state.chosen_indices.remove((i, "flip"))
            
            st.markdown("---")
            st.write("**현재 선택된 이미지:**")
            images_to_use = []
            for idx, orientation in st.session_state.chosen_indices:
                img_to_add = extracted_images[idx]
                if orientation == "flip":
                    img_to_add = ImageOps.mirror(img_to_add)
                images_to_use.append(img_to_add)
            
            if images_to_use:
                st.image(images_to_use, width=150)
            else:
                st.write("선택된 이미지가 없습니다.")
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        else:
            st.warning("추출할 이미지를 찾지 못했습니다."); images_to_use = []

        st.markdown("---")
        if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not openai_api_key)):
            client = OpenAI(api_key=openai_api_key)
            pdf_stream.seek(0)
            full_text = "".join(p.get_text() for p in fitz.open(stream=pdf_stream, filetype="pdf"))
            
            summaries = extract_and_summarize(client, full_text)
            
            with st.spinner("포스터를 생성합니다..."):
                title = getattr(paper_info, 'title', paper_info.get('title', ''))
                authors = [str(a) for a in getattr(paper_info, 'authors', [])]
                arxiv_link = getattr(paper_info, 'entry_id', None)
                
                poster_image = create_3_column_poster(title, authors, summaries, images_to_use, arxiv_link)
                st.success("🎉 포스터 생성 완료!")
                st.image(poster_image, use_container_width=True)
                
                img_byte_arr = BytesIO(); poster_image.save(img_byte_arr, format='PNG')
                st.download_button("📥 포스터 다운로드", img_byte_arr.getvalue(), "poster.png", "image/png")
