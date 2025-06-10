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
st.set_page_config(page_title="PosterGenius Assistant v6", layout="wide")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 48)
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 28)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 20)
        font_caption = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 16)
        return font_b, font_rl, font_rs, font_caption
    except IOError:
        st.error(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다.")
        return None, None, None, None

font_bold, font_regular_large, font_regular_small, font_caption = load_font("NotoSansKR-Bold.otf")


# --- 핵심 기능 함수 (이전과 동일) ---
def extract_all_images_from_pdf(pdf_stream):
    images = []
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        for page in doc:
            for img_info in page.get_images(full=True):
                if img_info[0] < 0 or img_info[2] < 100 or img_info[3] < 100: continue
                base_image = doc.extract_image(img_info[0])
                pil_image = Image.open(BytesIO(base_image["image"]))
                if pil_image.mode != "RGB": pil_image = pil_image.convert("RGB")
                images.append(pil_image)
        return images
    except Exception as e:
        st.warning(f"이미지 추출 중 오류: {e}"); return []

def extract_sections_with_gpt(client, text):
    st.info("GPT가 논문 전체 구조를 분석하여 주요 섹션을 추출합니다...")
    system_prompt = "You are an expert academic assistant. Your task is to extract the full text content of the \"Introduction\", \"Methodology\", and \"Results\" sections from the provided academic paper text. For \"Methodology\", also look for \"Methods\". For \"Results\", also look for \"Experiments\". Respond ONLY with a valid JSON object with three keys: \"introduction\", \"methodology\", \"results\". If a section cannot be found, the value should be an empty string."
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text[:15000]}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"GPT 기반 섹션 추출 중 오류: {e}"); return {"introduction": "", "methodology": "", "results": "섹션 추출 실패."}

def summarize_text_with_gpt(client, text, section_name):
    if not text.strip(): return f"[{section_name} 섹션의 내용을 찾지 못했습니다.]"
    try:
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "system", "content": "You are a helpful assistant that summarizes academic papers in Korean."}, {"role": "user", "content": f"다음 {section_name}을 한국어 3-4문장으로 요약해줘:\n\n{text}"}])
        return response.choices[0].message.content
    except Exception as e: return f"[{section_name} 요약 실패]"


# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: 3단 레이아웃 포스터 생성 함수 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def create_3_column_poster(title, authors, summaries, images=[], arxiv_link=None):
    width, height = 1800, 1000  # 가로형 크기 및 비율 조정
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

    # --- 헤더 ---
    d.rectangle([(0, 0), (width, 120)], fill="#F0F2F6")
    if arxiv_link:
        qr_img = qrcode.make(arxiv_link).resize((90, 90)); img.paste(qr_img, (width - 120, 15))
    draw_multiline_text((40, 30), title, font_bold, 1600, "#0E1117")
    
    # --- 3단 레이아웃 설정 ---
    margin, gap = 40, 40
    col_width = (width - 2 * margin - 2 * gap) // 3
    col1_x, col2_x, col3_x = margin, margin + col_width + gap, margin + 2 * (col_width + gap)
    current_y = [150] * 3 # 각 단의 y 위치

    def draw_section(col_index, title, content):
        col_x = [col1_x, col2_x, col3_x][col_index]
        y = current_y[col_index]
        y = draw_multiline_text((col_x, y), title, font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col_x, y), (col_x + col_width, y)], fill="#DDDDDD", width=2)
        y += 15
        y = draw_multiline_text((col_x, y), content, font_regular_small, col_width, "#31333F")
        current_y[col_index] = y + 30

    # --- 1단: Introduction & Methodology ---
    if "introduction" in summaries: draw_section(0, "Introduction", summaries["introduction"])
    if "methodology" in summaries: draw_section(0, "Methodology", summaries["methodology"])
        
    # --- 2단: Results ---
    if "results" in summaries: draw_section(1, "Results", summaries["results"])

    # --- 3단: Figures & Tables ---
    if images:
        y = current_y[2]
        y = draw_multiline_text((col3_x, y), "Figures & Tables", font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col3_x, y), (col3_x + col_width, y)], fill="#DDDDDD", width=2)
        y += 15
        for i, key_image in enumerate(images):
            key_image.thumbnail((col_width, col_width)) # 이미지 크기 조절
            img.paste(key_image, (col3_x, y))
            y += key_image.height + 5
            draw_multiline_text((col3_x, y), f"[Fig. {i+1}]", font_caption, col_width, "#888888")
            y += 25
        current_y[2] = y

    return img

# --- Streamlit App UI ---
if font_bold:
    st.title("📄➡️🖼️ PosterGenius Assistant (v6)")
    st.markdown("AI가 논문을 분석/요약하고, 사용자가 **여러 이미지를 선택**하면 **3단 가로형 포스터**를 생성합니다.")

    with st.sidebar:
        st.header("⚙️ 설정"); openai_api_key = st.secrets.get("OPENAI_API_KEY")
        if not openai_api_key: st.error("API 키를 찾을 수 없습니다.")
        input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

    pdf_stream, paper_info = None, None
    # ... (논문 로딩 부분은 이전과 동일)
    if input_option == 'arXiv ID':
        arxiv_id_input = st.text_input("2. 논문 arXiv ID 입력", "1703.06868")
        if arxiv_id_input:
            try:
                paper_info = arxiv.Search(id_list=[arxiv_id_input]).results().__next__()
                if paper_info:
                    pdf_stream = BytesIO(requests.get(paper_info.pdf_url).content)
                    st.success(f"**{paper_info.title}** 로드 완료!")
            except StopIteration:
                st.error("해당 ID의 논문을 찾을 수 없습니다. ID를 확인해주세요.")
    else:
        uploaded_file = st.file_uploader("2. 논문 PDF 업로드", type="pdf")
        if uploaded_file:
            paper_info = {"title": uploaded_file.name.replace(".pdf", "")}
            pdf_stream = BytesIO(uploaded_file.getvalue())


    if 'selected_images' not in st.session_state:
        st.session_state.selected_images = []

    if pdf_stream:
        st.markdown("---")
        st.subheader("3. 포스터에 포함할 이미지 선택 (다중 선택 가능)")
        extracted_images = extract_all_images_from_pdf(pdf_stream)
        
        if extracted_images:
            # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: 멀티 이미지 선택 UI ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
            options = [f"이미지 {i+1}" for i in range(len(extracted_images))]
            selected_options = st.multiselect("포스터에 넣을 이미지를 모두 선택하세요.", options)
            
            st.write("---")
            # 썸네일과 좌우반전 체크박스 표시
            for i, image in enumerate(extracted_images):
                st.image(image, caption=f"이미지 {i+1}", width=200)
                if st.checkbox(f"이미지 {i+1} 좌우 반전", key=f"flip_{i}"):
                    st.session_state.selected_images.append({"index": i, "flipped": True, "image": ImageOps.mirror(image)})
                else:
                    st.session_state.selected_images.append({"index": i, "flipped": False, "image": image})
                st.write("---")
            
            images_to_use = [item["image"] for item in st.session_state.selected_images if f"이미지 {item['index']+1}" in selected_options]

        else:
            st.warning("추출할 이미지를 찾지 못했습니다."); images_to_use = []

        st.markdown("---")
        if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not openai_api_key)):
            client = OpenAI(api_key=openai_api_key)
            pdf_stream.seek(0)
            full_text = "".join(p.get_text() for p in fitz.open(stream=pdf_stream, filetype="pdf"))
            extracted_sections = extract_sections_with_gpt(client, full_text)
            
            summaries = {}
            with st.spinner("각 섹션 내용을 요약하는 중..."):
                for s_name, s_text in extracted_sections.items():
                    summaries[s_name] = summarize_text_with_gpt(client, s_text, s_name)
            
            with st.spinner("포스터를 생성합니다..."):
                title = getattr(paper_info, 'title', paper_info.get('title', ''))
                authors = [str(a) for a in getattr(paper_info, 'authors', [])]
                arxiv_link = getattr(paper_info, 'entry_id', None)
                
                poster_image = create_3_column_poster(title, authors, summaries, images_to_use, arxiv_link)
                st.success("🎉 포스터 생성 완료!")
                # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선: use_container_width 사용 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
                st.image(poster_image, use_container_width=True)
                
                img_byte_arr = BytesIO()
                poster_image.save(img_byte_arr, format='PNG')
                st.download_button("📥 포스터 다운로드", img_byte_arr.getvalue(), "poster.png", "image/png")