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
st.set_page_config(page_title="PosterGenius Assistant v7.1", layout="wide")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 52)
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 32)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 24)
        font_caption = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 18)
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
                
                # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 오류 수정: .determinant -> .det ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
                # 이미지의 변환 행렬(transformation matrix)을 확인하여 반전 여부 감지
                tm = fitz.Matrix(img_info[1], img_info[2], img_info[3], img_info[4], 0, 0)
                is_flipped = tm.det < 0 # .det가 올바른 속성명입니다.
                # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

                base_image = doc.extract_image(img_info[0])
                pil_image = Image.open(BytesIO(base_image["image"]))
                if pil_image.mode != "RGB": pil_image = pil_image.convert("RGB")
                
                if is_flipped:
                    pil_image = ImageOps.mirror(pil_image)

                images.append(pil_image)
        return images
    except Exception as e:
        st.warning(f"이미지 추출 중 오류: {e}"); return []

def extract_and_summarize(client, text):
    st.info("GPT가 논문 전체 구조를 분석하여 주요 섹션을 추출하고 요약합니다...")
    system_prompt = "You are an expert academic assistant. Your task is to analyze an academic paper's text. First, extract the content of the 'Introduction', 'Methodology', and 'Results' sections. For 'Methodology', also accept 'Methods'. For 'Results', also accept 'Experiments'. Then, summarize each extracted section in 3-4 sentences in KOREAN. Respond ONLY with a valid JSON object. The JSON object must have keys 'introduction_summary', 'methodology_summary', and 'results_summary'. If a section is not found, its summary should be a string stating that. Do not include explanations outside the JSON."
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text[:15000]}],
            response_format={"type": "json_object"}
        )
        summaries = json.loads(response.choices[0].message.content)
        if "introduction_summary" not in summaries: summaries["introduction_summary"] = "[Introduction 섹션을 찾지 못했습니다.]"
        if "methodology_summary" not in summaries: summaries["methodology_summary"] = "[Methodology 섹션을 찾지 못했습니다.]"
        if "results_summary" not in summaries: summaries["results_summary"] = "[Results 섹션을 찾지 못했습니다.]"
        return summaries
    except Exception as e:
        st.error(f"GPT 기반 추출/요약 중 오류: {e}"); return {k: "처리 실패" for k in ["introduction_summary", "methodology_summary", "results_summary"]}

def create_readable_poster(title, authors, summaries, key_image=None, arxiv_link=None):
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
    
    margin, gap = 40, 60
    col_width = (width - 2 * margin - gap) // 2
    col1_x, col2_x = margin, margin + col_width + gap
    y1, y2 = 150, 150

    def draw_section(col_x, y_start, title, content):
        y = y_start
        y = draw_multiline_text((col_x, y), title, font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col_x, y), (col_x + col_width, y)], fill="#DDDDDD", width=2)
        y += 15
        y = draw_multiline_text((col_x, y), content, font_regular_small, col_width, "#31333F")
        return y + 30

    y1 = draw_section(col1_x, y1, "Introduction", summaries.get('introduction_summary', ''))
    y1 = draw_section(col1_x, y1, "Methodology", summaries.get('methodology_summary', ''))
    
    y2 = draw_multiline_text((col2_x, y2), "Results", font_regular_large, col_width, "#4A6CFA", 5)
    d.line([(col2_x, y2), (col2_x + col_width, y2)], fill="#DDDDDD", width=2)
    y2 += 15
    if key_image:
        text_height_limit = y2 + (height - y2) * 0.6
        final_y = draw_multiline_text((col2_x, y2), summaries.get('results_summary', ''), font_regular_small, col_width, "#31333F")
        image_y_start = final_y + 20
        if image_y_start < height - 100:
            key_image.thumbnail((col_width, height - image_y_start - margin))
            img.paste(key_image, (col2_x, image_y_start))
    else:
        draw_multiline_text((col2_x, y2), summaries.get('results_summary', ''), font_regular_small, col_width, "#31333F")
        
    return img

# --- Streamlit App UI ---
if font_bold:
    st.title("📄➡️🖼️ PosterGenius Assistant (v7.1)")
    st.markdown("AI가 논문을 **분석/요약**하고, 사용자가 **핵심 이미지를 지정**하면 **가독성 높은 2단 가로형 포스터**를 생성합니다.")

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
                    with st.spinner('논문 PDF 다운로드 중...'):
                        pdf_stream = BytesIO(requests.get(paper_info.pdf_url).content)
                    st.success(f"**{paper_info.title}** 로드 완료!")
            except StopIteration: st.error("해당 ID의 논문을 찾을 수 없습니다.")
    else:
        uploaded_file = st.file_uploader("2. 논문 PDF 업로드", type="pdf")
        if uploaded_file:
            paper_info = {"title": uploaded_file.name.replace(".pdf", "")}; pdf_stream = BytesIO(uploaded_file.getvalue())

    if pdf_stream:
        st.markdown("---")
        st.subheader("3. 포스터에 포함할 핵심 이미지 선택")
        
        extracted_images = extract_images_from_pdf(pdf_stream)
        
        if extracted_images:
            cols = st.columns(len(extracted_images))
            for i, image in enumerate(extracted_images):
                with cols[i]:
                    st.image(image, caption=f"이미지 {i+1}", use_container_width=True)

            options = ["선택 안함"] + [f"이미지 {i+1}" for i in range(len(extracted_images))]
            selected_option = st.selectbox("'Results'와 함께 배치할 핵심 이미지를 하나만 선택하세요.", options)
            
            image_to_use = None
            if selected_option != "선택 안함":
                selected_index = int(selected_option.split(" ")[1]) - 1
                image_to_use = extracted_images[selected_index]
        else:
            st.warning("추출할 이미지를 찾지 못했습니다."); image_to_use = None

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
                
                poster_image = create_readable_poster(title, authors, summaries, image_to_use, arxiv_link)
                st.success("🎉 포스터 생성 완료!")
                st.image(poster_image, use_container_width=True)
                
                img_byte_arr = BytesIO()
                poster_image.save(img_byte_arr, format='PNG')
                st.download_button("📥 포스터 다운로드", img_byte_arr.getvalue(), "poster.png", "image/png")
