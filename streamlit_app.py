import streamlit as st
import arxiv
import fitz  # PyMuPDF
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from io import BytesIO
import qrcode
import json

# --- 페이지 설정 및 기본 스타일 ---
st.set_page_config(page_title="PosterGenius", layout="wide")

# [개선] st.session_state 초기화: 앱의 상태를 저장하여 불필요한 재실행을 방지
if 'step' not in st.session_state:
    st.session_state.step = 1
    st.session_state.api_key_valid = False # API 키 유효성 상태 추가
    st.session_state.pdf_stream = None
    st.session_state.paper_info = None
    st.session_state.full_text = None
    st.session_state.extracted_images = None
    st.session_state.summaries = None
    st.session_state.selected_images = []
    st.session_state.final_poster = None

# --- 폰트 로드 ---
@st.cache_data
def load_font(font_filename="NotoSansKR-Bold.otf"):
    try:
        base_font_regular = font_filename.replace("Bold", "Regular")
        return {
            "title": ImageFont.truetype(font_filename, 60),
            "section": ImageFont.truetype(base_font_regular, 38),
            "body": ImageFont.truetype(base_font_regular, 26),
            "caption": ImageFont.truetype(base_font_regular, 20)
        }
    except IOError:
        st.error(f"'{font_filename}' 폰트 파일을 찾을 수 없습니다. 앱 실행이 중단됩니다.")
        return None

# [개선] 색상 팔레트 정의
COLOR_PALETTES = {
    "Academic Blue": {"bg": "#FFFFFF", "primary": "#0033A0", "secondary": "#F0F2F6", "text": "#333333", "header_text": "#0E1117"},
    "Modern Graphite": {"bg": "#FFFFFF", "primary": "#333333", "secondary": "#EAEAEA", "text": "#111111", "header_text": "#000000"},
    "Warm Beige": {"bg": "#FDFBF7", "primary": "#D2691E", "secondary": "#F5F1E9", "text": "#4A3F35", "header_text": "#2C231E"},
}

# --- 핵심 기능 함수 (이전과 동일) ---

def extract_text_and_images_from_pdf(pdf_stream):
    """PDF에서 텍스트와 이미지를 한 번에 추출합니다."""
    images = []
    full_text = ""
    try:
        pdf_stream.seek(0)
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        for page_num, page in enumerate(doc):
            full_text += page.get_text()
            for img_info in page.get_image_info(xrefs=True):
                if img_info['width'] < 150 or img_info['height'] < 150:
                    continue
                
                base_image = doc.extract_image(img_info['xref'])
                pil_image = Image.open(BytesIO(base_image["image"]))
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                tm = img_info['transform']
                if (tm[0] * tm[3] - tm[1] * tm[2]) < 0:
                    pil_image = ImageOps.mirror(pil_image)
                
                images.append({"img": pil_image, "page": page_num + 1})
        return full_text, images
    except Exception as e:
        st.warning(f"PDF 처리 중 오류 발생: {e}")
        return "", []

def summarize_text(client, text):
    """GPT를 사용하여 텍스트의 각 섹션을 요약합니다."""
    system_prompt = """
    You are a professional academic assistant. Analyze the provided academic paper text.
    1.  Identify and extract the core content for 'Introduction', 'Methodology' (or 'Methods'), 'Results' (or 'Experiments'), and 'Conclusion' sections.
    2.  Summarize each section concisely in 3-4 sentences in KOREAN.
    3.  If a section is not found, its summary should be an empty string.
    4.  Respond ONLY with a valid JSON object with keys: 'introduction_summary', 'methodology_summary', 'results_summary', 'conclusion_summary'. Do not include any explanations outside of the JSON structure.
    """
    try:
        with st.spinner("GPT가 논문 구조를 분석하고 핵심 내용을 요약 중입니다... (1/2)"):
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text[:12000] + "\n\n... (omitted) ...\n\n" + text[-4000:]}
                ],
                response_format={"type": "json_object"}
            )
        summaries = json.loads(response.choices[0].message.content)
        return summaries
    except Exception as e:
        st.error(f"GPT 요약 중 오류 발생: {e}")
        return {k: "요약 생성에 실패했습니다. API 키나 네트워크 상태를 확인해주세요." for k in ["introduction_summary", "methodology_summary", "results_summary", "conclusion_summary"]}

def draw_multiline_text(draw, position, text, font, max_width, fill, spacing=12):
    """Pillow을 사용하여 여러 줄의 텍스트를 그립니다."""
    x, y = position; words = text.split()
    if not words: return y
    lines = []; line = ""
    for word in words:
        if draw.textlength(line + word + " ", font=font) <= max_width: line += word + " "
        else: lines.append(line); line = word + " "
    lines.append(line)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        try: y += font.getbbox("A")[3] + spacing
        except AttributeError: y += font.getsize("A")[1] + spacing
    return y

def create_poster(title, authors, sections, images, theme, arxiv_link):
    """입력된 정보와 디자인 테마로 포스터 이미지를 생성합니다."""
    width, height = 1920, 1080; colors = COLOR_PALETTES[theme]; fonts = load_font()
    img = Image.new('RGB', (width, height), color=colors["bg"]); draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width, 150)], fill=colors["secondary"])
    current_y = 50; current_y = draw_multiline_text(draw, (60, current_y), title, fonts["title"], 1650, colors["header_text"]); current_y += 5
    draw_multiline_text(draw, (60, current_y), ", ".join(authors), fonts["body"], 1650, colors["text"], spacing=8)
    if arxiv_link: qr_img = qrcode.make(arxiv_link).resize((110, 110)); img.paste(qr_img, (width - 150, 20))
    margin, gap = 60, 40; col_width = (width - 2 * margin - 2 * gap) // 3
    col_x_positions = [margin, margin + col_width + gap, margin + 2 * (col_width + gap)]; col_y_positions = [200, 200, 200]
    content_items = []
    for sec_title, sec_content in sections.items():
        if sec_content: content_items.append({"type": "text", "title": sec_title.replace("_", " ").title(), "content": sec_content})
    if images: content_items.append({"type": "image", "title": "Figures & Tables", "images": images})
    for item in content_items:
        target_col_index = col_y_positions.index(min(col_y_positions)); col_x = col_x_positions[target_col_index]; y = col_y_positions[target_col_index]
        y = draw_multiline_text(draw, (col_x, y), item['title'], fonts["section"], col_width, colors["primary"], spacing=8)
        draw.line([(col_x, y), (col_x + col_width, y)], fill=colors["secondary"], width=3); y += 25
        if item["type"] == "text": y = draw_multiline_text(draw, (col_x, y), item["content"], fonts["body"], col_width, colors["text"], spacing=10)
        elif item["type"] == "image":
            for i, key_image in enumerate(item["images"]):
                key_image.thumbnail((col_width, col_width)); img.paste(key_image, (col_x, y)); y += key_image.height + 10
                draw_multiline_text(draw, (col_x, y), f"[Fig. {i+1}]", fonts["caption"], col_width, "#666666"); y += 35
        col_y_positions[target_col_index] = y + 50
    return img


# --- Streamlit App UI ---
fonts = load_font()
if fonts:
    st.title("📄➡️🖼️ PosterGenius")
    st.markdown("AI 어시스턴트와 함께 논문을 세련된 포스터로 변환해보세요. **3단계**로 손쉽게 완성할 수 있습니다.")

    # [수정] st.secrets에서 API 키를 직접 로드
    try:
        openai_api_key = st.secrets["OPENAI_API_KEY"]
        st.session_state.api_key_valid = True
    except KeyError:
        openai_api_key = None
        st.session_state.api_key_valid = False

    with st.sidebar:
        st.header("🎨 디자인 설정")
        st.session_state.color_theme = st.selectbox("포스터 색상 테마", list(COLOR_PALETTES.keys()))
        st.markdown("---")
        # [수정] API 키 입력 UI를 상태 피드백으로 대체
        if st.session_state.api_key_valid:
            st.success("✅ OpenAI API Key가 연결되었습니다.")
        else:
            st.error("오류: OpenAI API Key가 설정되지 않았습니다. Streamlit Cloud의 'Secrets'에 'OPENAI_API_KEY'를 추가해주세요.")

    tab1, tab2, tab3 = st.tabs(["[ 1단계: 논문 입력 및 분석 ]", "[ 2단계: 내용 편집 ]", "[ 3단계: 포스터 생성 ]"])

    with tab1:
        st.header("1. 논문 정보 입력")
        input_option = st.radio("입력 방식 선택:", ('arXiv ID', 'PDF 파일 업로드'), horizontal=True)

        if input_option == 'arXiv ID':
            arxiv_id_input = st.text_input("논문 arXiv ID", "2005.12872", help="예: 2005.12872")
            if st.button("arXiv에서 논문 가져오기", type="primary"):
                if arxiv_id_input:
                    try:
                        with st.spinner('arXiv 서버에서 논문 정보를 다운로드 중입니다...'):
                            paper = arxiv.Search(id_list=[arxiv_id_input]).results().__next__()
                            pdf_stream = BytesIO(requests.get(paper.pdf_url).content)
                            st.session_state.paper_info = {"title": paper.title.replace('\n', ' '), "authors": [str(a) for a in paper.authors], "arxiv_link": paper.entry_id}
                            st.session_state.pdf_stream = pdf_stream
                        st.success(f"**{st.session_state.paper_info['title']}** 로드 완료!")
                        st.session_state.step = 2
                    except StopIteration: st.error("해당 ID의 논문을 찾을 수 없습니다.")
                    except Exception as e: st.error(f"논문 다운로드 중 오류 발생: {e}")
                else: st.warning("arXiv ID를 입력해주세요.")
        else:
            uploaded_file = st.file_uploader("논문 PDF 파일 업로드", type="pdf")
            if uploaded_file:
                st.session_state.pdf_stream = BytesIO(uploaded_file.getvalue())
                st.session_state.paper_info = {"title": uploaded_file.name.replace(".pdf", ""), "authors": ["Manually Enter Authors"], "arxiv_link": None}
                st.success(f"**{st.session_state.paper_info['title']}** 업로드 완료!")
                st.session_state.step = 2

        if st.session_state.step >= 2:
            st.markdown("---")
            st.subheader("2. 핵심 내용 자동 분석")
            # [수정] 버튼 비활성화 조건을 API 키 유효성으로 변경
            if st.button("텍스트/이미지 추출 및 AI 요약 실행", disabled=(not st.session_state.api_key_valid)):
                with st.spinner("PDF에서 텍스트와 이미지를 추출 중입니다..."):
                    st.session_state.full_text, st.session_state.extracted_images = extract_text_and_images_from_pdf(st.session_state.pdf_stream)
                
                if st.session_state.full_text:
                    client = OpenAI(api_key=openai_api_key) # 로드된 API 키 사용
                    st.session_state.summaries = summarize_text(client, st.session_state.full_text)
                    st.info("AI 요약이 완료되었습니다. **2단계 탭에서 결과를 확인하고 수정**할 수 있습니다.")
                    st.session_state.step = 3
                else: st.error("PDF에서 텍스트를 추출하지 못했습니다.")

    with tab2:
        if st.session_state.step < 2: st.info("⬅️ 먼저 1단계에서 논문을 입력하고 분석을 실행해주세요.")
        else:
            st.header("포스터 내용 편집")
            st.info("AI가 생성한 내용을 검토하고 자유롭게 수정하세요.")
            
            st.session_state.paper_info['title'] = st.text_input("논문 제목", st.session_state.paper_info['title'])
            st.session_state.paper_info['authors'] = [s.strip() for s in st.text_area("저자 (쉼표로 구분)", ", ".join(st.session_state.paper_info['authors'])).split(',')]
            
            if st.session_state.summaries:
                st.markdown("---")
                st.subheader("섹션별 요약 내용")
                st.session_state.summaries['introduction_summary'] = st.text_area("Introduction 요약", st.session_state.summaries.get('introduction_summary', ''), height=150)
                st.session_state.summaries['methodology_summary'] = st.text_area("Methodology 요약", st.session_state.summaries.get('methodology_summary', ''), height=150)
                st.session_state.summaries['results_summary'] = st.text_area("Results 요약", st.session_state.summaries.get('results_summary', ''), height=150)
                st.session_state.summaries['conclusion_summary'] = st.text_area("Conclusion 요약", st.session_state.summaries.get('conclusion_summary', ''), height=150)
            
            if st.session_state.extracted_images:
                st.markdown("---")
                st.subheader("포스터에 포함할 이미지 선택")
                options = [f"이미지 {i+1} (p.{img['page']})" for i, img in enumerate(st.session_state.extracted_images)]
                selected_options = st.multiselect("이미지를 모두 선택하세요:", options)
                st.session_state.selected_images = [st.session_state.extracted_images[int(opt.split(" ")[1]) - 1]['img'] for opt in selected_options]
                st.write("**추출된 이미지 썸네일:**")
                st.image([img['img'] for img in st.session_state.extracted_images], caption=options, width=150)

    with tab3:
        if st.session_state.step < 3: st.info("⬅️ 1, 2단계를 완료하고 포스터를 생성하세요.")
        else:
            st.header("최종 포스터 생성")
            st.markdown("모든 설정이 완료되었습니다. 아래 버튼을 눌러 포스터를 만드세요.")
            if st.button("🚀 포스터 생성하기!", type="primary"):
                with st.spinner("디자인 요소를 조합하여 포스터를 생성합니다... (2/2)"):
                    sections_to_render = {
                        "Introduction": st.session_state.summaries['introduction_summary'],
                        "Methodology": st.session_state.summaries['methodology_summary'],
                        "Results": st.session_state.summaries['results_summary'],
                        "Conclusion": st.session_state.summaries['conclusion_summary'],
                    }
                    poster_image = create_poster(
                        title=st.session_state.paper_info['title'], authors=st.session_state.paper_info['authors'],
                        sections=sections_to_render, images=st.session_state.selected_images,
                        theme=st.session_state.color_theme, arxiv_link=st.session_state.paper_info.get('arxiv_link')
                    )
                    st.session_state.final_poster = poster_image

            if st.session_state.final_poster:
                st.success("🎉 포스터 생성이 완료되었습니다!")
                st.image(st.session_state.final_poster, use_container_width=True)
                img_byte_arr = BytesIO()
                st.session_state.final_poster.save(img_byte_arr, format='PNG')
                st.download_button(
                    label="📥 포스터 다운로드 (PNG)", data=img_byte_arr.getvalue(),
                    file_name=f"poster_{st.session_state.paper_info['title'][:20].replace(' ', '_')}.png", mime="image/png"
                )
