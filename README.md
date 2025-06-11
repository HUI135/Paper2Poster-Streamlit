# 📄➡️🖼️ PosterGenius Assistant (v7)

복잡한 학술 논문을 발표용 포스터 초안으로 빠르게 변환해주는 AI 비서입니다. 논문의 핵심 내용을 자동으로 추출하고 요약하며, 사용자가 선정한 주요 이미지를 통합하여 가독성 높은 가로형 포스터를 생성합니다.

이 프로젝트는 단순한 자동화 도구가 아닌, **AI가 지능적으로 재료를 준비하면 사용자가 최종 결정을 내리는 '협업'**에 초점을 맞추어 개발되었습니다. 이를 통해 연구자들은 포스터 제작에 드는 시간을 획기적으로 줄이고, 콘텐츠에 더 집중할 수 있습니다.

![앱 데모 스크린샷](https://i.imgur.com/your-screenshot-url.png)
*(안내: 이 줄을 실제 앱 실행 화면 스크린샷 URL로 교체해주세요.)*

## ✨ 핵심 기능 (Key Features)

* **지능형 섹션 분석 (GPT-4 기반):** 정해진 규칙이 아닌, GPT의 강력한 문맥 이해 능력을 통해 논문 본문에서 Introduction, Methodology, Results 섹션을 정확하게 추출합니다.
* **핵심 내용 자동 요약 (한국어):** 추출된 각 섹션의 내용을 AI가 유려한 한국어 문장으로 3-4 문장으로 요약합니다.
* **자동 이미지 추출 및 교정:** PDF에서 의미 있는 크기의 이미지를 모두 추출하고, 일부 PDF에서 발생하는 '좌우 반전' 문제를 자동으로 감지하여 교정합니다.
* **사용자 중심의 콘텐츠 선택:** 추출된 이미지들을 UI에 나열하여, 사용자가 포스터의 핵심이 될 이미지를 직접 선택할 수 있도록 합니다.
* **가독성 높은 2단 가로형 레이아웃:** 학회 발표 환경에 최적화된 가로형 포스터를 생성하며, [서론/방법론] - [결과/핵심 이미지]의 2단 구조로 내용을 명확하게 전달합니다.
* **다양한 입력 지원:** `arXiv ID` 또는 `PDF 파일` 직접 업로드를 모두 지원합니다.

## ⚙️ 작동 방식 (How It Works)

1.  **입력 (Input):** 사용자가 `arXiv ID` 또는 `PDF 파일`을 업로드합니다.
2.  **분석 (Analysis):**
    * `PyMuPDF`를 사용하여 텍스트 전체와 모든 이미지를 추출합니다.
    * `Pillow`과 `PyMuPDF`의 메타데이터를 분석하여 뒤집힌 이미지를 바로잡습니다.
3.  **AI 처리 (AI Processing):**
    * `GPT-4 Turbo`가 논문 전체 텍스트의 구조를 이해하고 주요 섹션(서론, 방법론, 결과)을 정확히 분리합니다.
    * `GPT-3.5 Turbo`가 각 섹션의 내용을 한국어로 간결하게 요약합니다.
4.  **사용자 상호작용 (User Interaction):**
    * `Streamlit` UI를 통해 추출된 이미지 목록을 보여줍니다.
    * 사용자는 이 중 포스터에 포함할 '핵심 이미지' 하나를 선택합니다.
5.  **생성 (Generation):**
    * `Pillow` 라이브러리가 AI 요약본과 사용자가 선택한 이미지를 미리 디자인된 2단 가로형 템플릿에 배치하여 최종 포스터 이미지를 생성합니다.

## 🚀 시작하기 (Getting Started)

이 프로젝트를 로컬 환경에서 실행하기 위한 안내입니다.

### 준비물 (Prerequisites)

* Python 3.8 이상
* `pip` (Python 패키지 관리자)

### 설치 (Installation)

1.  **프로젝트 복제:**
    ```bash
    git clone [https://github.com/your-username/PosterGenius-Assistant.git](https://github.com/your-username/PosterGenius-Assistant.git)
    cd PosterGenius-Assistant
    ```
    *(안내: `your-username/PosterGenius-Assistant.git`을 실제 GitHub 저장소 주소로 변경해주세요.)*

2.  **필요한 라이브러리 설치:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **API 키 설정:**
    * 프로젝트 루트 디렉토리에 `.streamlit` 이라는 이름의 폴더를 생성합니다.
    * 생성한 `.streamlit` 폴더 안에 `secrets.toml` 파일을 만듭니다.
    * `secrets.toml` 파일에 아래와 같이 자신의 OpenAI API 키를 입력하고 저장합니다.
        ```toml
        # .streamlit/secrets.toml
        OPENAI_API_KEY = "sk-..."
        ```

## ▶️ 사용법 (Usage)

프로젝트 설정이 완료되면, 터미널에서 아래 명령어를 실행하여 Streamlit 앱을 실행합니다.

```bash
streamlit run streamlit_app.py