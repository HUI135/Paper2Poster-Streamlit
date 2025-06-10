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
st.set_page_config(page_title="PosterGenius Assistant v5", layout="wide")

# --- 폰트 로드 ---
def load_font(font_filename):
    try:
        font_b = ImageFont.truetype(font_filename, 48)  # 가로형에 맞게 폰트 크기 조정
        font_rl = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 28)
        font_rs = ImageFont.truetype(font_filename.replace("Bold", "Regular"), 22)
        return font_b, font_rl, font_rs
    except IOError:
        st.error(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다.")
        return None, None, None

font_bold, font_regular_large, font_regular_small = load_font("NotoSansKR-Bold.otf")

# --- 핵심 기능 함수 ---

def extract_all_images_from_pdf(pdf_stream):
    images = []
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        for page in doc:
            for img_info in page.get_images(full=True):
                if img_info[0] < 0: continue # In-line image skip
                if img_info[2] < 100 or img_info[3] < 100: continue
                
                base_image = doc.extract_image(img_info[0])
                pil_image = Image.open(BytesIO(base_image["image"]))
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")
                images.append(pil_image)
        return images
    except Exception as e:
        st.warning(f"이미지 추출 중 오류: {e}")
        return []

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선 3: GPT를 이용한 섹션 추출 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def extract_sections_with_gpt(client, text):
    """GPT를 사용하여 주요 섹션의 내용을 JSON 형태로 추출합니다."""
    st.info("GPT가 논문 전체 구조를 분석하여 주요 섹션을 추출합니다. 잠시만 기다려주세요...")
    system_prompt = """
    You are an expert academic assistant. Your task is to extract the full text content of the "Introduction", "Methodology", and "Results" sections from the provided academic paper text.
    - For "Methodology", also look for "Methods" or "Materials and Methods".
    - For "Results", also look for "Experiments" or "Experimental Results".
    - Respond ONLY with a valid JSON object.
    - The JSON object must have three keys: "introduction", "methodology", "results".
    - The value for each key should be the complete, extracted text of that section.
    - If a section cannot be found, the value should be an empty string "".
    - Do not include any explanations or text outside of the JSON object.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",  # 구조 분석에는 더 성능 좋은 모델을 권장
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:15000]} # 토큰 제한 고려
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"GPT 기반 섹션 추출 중 오류 발생: {e}")
        return {"introduction": "", "methodology": "", "results": "섹션 추출에 실패했습니다."}

def summarize_text_with_gpt(client, text, section_name):
    if not text.strip(): return f"[{section_name} 섹션의 내용을 찾지 못했습니다.]"
    # ... (요약 함수는 이전과 동일)
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant that summarizes academic papers in Korean."},
                      {"role": "user", "content": f"다음 {section_name}을 한국어 3-4문장으로 요약해줘:\n\n{text}"}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[{section_name} 요약 실패]"

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선 1: 가로형 포스터 생성 함수 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
def create_landscape_poster(title, authors, summaries, key_image=None, arxiv_link=None):
    width, height = 1600, 900  # 가로형 크기
    img = Image.new('RGB', (width, height), color="#FFFFFF")
    d = ImageDraw.Draw(img)
    
    def draw_multiline_text(position, text, font, max_width, fill, spacing=10):
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
            y += font.getbbox("A")[3] + spacing
        return y

    # --- 헤더 (상단 전체) ---
    d.rectangle([(0, 0), (width, 120)], fill="#F0F2F6")
    if arxiv_link:
        qr_img = qrcode.make(arxiv_link).resize((90, 90))
        img.paste(qr_img, (width - 120, 15))
    draw_multiline_text((40, 30), title, font_bold, 1400, "#0E1117")
    
    # --- 2단 레이아웃 설정 ---
    col1_x, col2_x = 40, 840
    col_width = 720
    current_y1, current_y2 = 150, 150
    
    # --- 1단: Introduction & Image ---
    if "introduction" in summaries:
        current_y1 = draw_multiline_text((col1_x, current_y1), "Introduction", font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col1_x, current_y1), (col1_x + col_width, current_y1)], fill="#DDDDDD", width=2)
        current_y1 += 15
        current_y1 = draw_multiline_text((col1_x, current_y1), summaries["introduction"], font_regular_small, col_width, "#31333F")
        current_y1 += 30

    if key_image:
        key_image.thumbnail((col_width, 400))
        img.paste(key_image, (col1_x, current_y1))

    # --- 2단: Methodology & Results ---
    if "methodology" in summaries:
        current_y2 = draw_multiline_text((col2_x, current_y2), "Methodology", font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col2_x, current_y2), (col2_x + col_width, current_y2)], fill="#DDDDDD", width=2)
        current_y2 += 15
        current_y2 = draw_multiline_text((col2_x, current_y2), summaries["methodology"], font_regular_small, col_width, "#31333F")
        current_y2 += 30
        
    if "results" in summaries:
        current_y2 = draw_multiline_text((col2_x, current_y2), "Results", font_regular_large, col_width, "#4A6CFA", 5)
        d.line([(col2_x, current_y2), (col2_x + col_width, current_y2)], fill="#DDDDDD", width=2)
        current_y2 += 15
        current_y2 = draw_multiline_text((col2_x, current_y2), summaries["results"], font_regular_small, col_width, "#31333F")

    return img

# --- Streamlit App UI ---
if font_bold:
    st.title("📄➡️🖼️ PosterGenius Assistant (v5)")
    st.markdown("AI가 논문을 **분석/요약**하고, 사용자가 **이미지를 선택**하면 **가로형 포스터 초안**을 생성합니다.")

    with st.sidebar:
        st.header("⚙️ 설정"); openai_api_key = st.secrets.get("OPENAI_API_KEY")
        if not openai_api_key: st.error("API 키를 찾을 수 없습니다.")
        input_option = st.radio("1. 입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'))

    pdf_stream, paper_info = None, None
    if input_option == 'arXiv ID':
        arxiv_id_input = st.text_input("2. 논문 arXiv ID 입력", "1703.06868")
        if arxiv_id_input:
            paper_info = arxiv.Search(id_list=[arxiv_id_input]).results().__next__()
            if paper_info:
                pdf_stream = BytesIO(requests.get(paper_info.pdf_url).content)
                st.success(f"**{paper_info.title}** 로드 완료!")
    else:
        uploaded_file = st.file_uploader("2. 논문 PDF 업로드", type="pdf")
        if uploaded_file:
            paper_info = {"title": uploaded_file.name.replace(".pdf", "")}
            pdf_stream = BytesIO(uploaded_file.getvalue())

    if pdf_stream:
        st.markdown("---")
        st.subheader("3. 포스터에 포함할 이미지 선택")
        extracted_images = extract_all_images_from_pdf(pdf_stream)
        
        selected_image, image_to_use = None, None
        if extracted_images:
            cols = st.columns(len(extracted_images))
            for i, image in enumerate(extracted_images):
                with cols[i]:
                    st.image(image, caption=f"이미지 {i+1}", use_column_width=True)
            
            selected_option = st.selectbox("포스터에 넣을 이미지를 선택하세요.", ["선택 안함"] + [f"이미지 {i+1}" for i in range(len(extracted_images))])
            if selected_option != "선택 안함":
                selected_image = extracted_images[int(selected_option.split(" ")[1]) - 1]
                # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 개선 2: 이미지 좌우 반전 옵션 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
                if st.checkbox("선택한 이미지 좌우 반전 (뒤집힌 경우 체크)"):
                    image_to_use = ImageOps.mirror(selected_image)
                else:
                    image_to_use = selected_image
        else:
            st.warning("추출할 이미지를 찾지 못했습니다.")

        st.markdown("---")
        if st.button("🚀 포스터 생성하기!", type="primary", disabled=(not openai_api_key)):
            client = OpenAI(api_key=openai_api_key)
            pdf_stream.seek(0)
            full_text = "".join(p.get_text() for p in fitz.open(stream=pdf_stream, filetype="pdf"))
            
            extracted_sections = extract_sections_with_gpt(client, full_text)
            
            summaries = {}
            with st.spinner("각 섹션 내용을 요약하는 중..."):
                for section_name, section_text in extracted_sections.items():
                    summaries[section_name] = summarize_text_with_gpt(client, section_text, section_name)
            
            with st.spinner("포스터를 생성합니다..."):
                title = getattr(paper_info, 'title', paper_info.get('title', ''))
                authors = [str(a) for a in getattr(paper_info, 'authors', [])]
                arxiv_link = getattr(paper_info, 'entry_id', None)
                
                poster_image = create_landscape_poster(title, authors, summaries, image_to_use, arxiv_link)
                st.success("🎉 포스터 생성 완료!")
                st.image(poster_image, use_column_width=True)
                
                img_byte_arr = BytesIO()
                poster_image.save(img_byte_arr, format='PNG')
                st.download_button("📥 포스터 다운로드", img_byte_arr.getvalue(), "poster.png", "image/png")