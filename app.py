"""Study Buddy - Streamlit user interface.

Only the UI lives here. The agent itself is in api_version/ and sdk_version/,
and the user chooses which of the two versions to run.

Run:  .\\.venv\\Scripts\\streamlit.exe run app.py
"""

import sys
import zipfile
from pathlib import Path

import streamlit as st
from docx import Document
from pptx import Presentation
from pypdf import PdfReader
from pypdf.errors import PdfReadError

ROOT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "api_version"), str(ROOT / "sdk_version")]

import study_buddy_api  # noqa: E402
import study_buddy_sdk  # noqa: E402

VERSIONS = {"API (requests)": study_buddy_api, "SDK (openai)": study_buddy_sdk}
DIFFICULTY_LABELS = {"easy": "קל", "medium": "בינוני", "hard": "קשה"}

# Streamlit is left-to-right by default; flip it for Hebrew, keep code/JSON left-to-right.
RTL_CSS = """
<style>
.stApp { direction: rtl; text-align: right; }
pre, code, [data-testid="stJson"] { direction: ltr; text-align: left; }
</style>
"""


SUPPORTED_FILE_TYPES = ["txt", "pptx", "pdf", "docx"]


def extract_text(uploaded_file) -> str:
    """Pull the plain text out of an uploaded file (text only - images are not read)."""
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pptx":
        slides = Presentation(uploaded_file).slides
        return "\n".join(shape.text_frame.text for slide in slides for shape in slide.shapes if shape.has_text_frame)
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(uploaded_file).pages)
    if suffix == ".docx":
        return "\n".join(paragraph.text for paragraph in Document(uploaded_file).paragraphs)
    return uploaded_file.getvalue().decode("utf-8")  # .txt


def read_study_material() -> str:
    """Return the text from the uploaded file, or from the text box."""
    uploaded_file = st.file_uploader("העלאת קובץ (txt, pptx, pdf, docx)", type=SUPPORTED_FILE_TYPES)
    pasted_text = st.text_area("או הדבקת טקסט:", height=200)
    if uploaded_file is None:
        return pasted_text
    try:
        return extract_text(uploaded_file)
    except UnicodeDecodeError:
        st.error("לא ניתן לקרוא את קובץ הטקסט. יש לשמור אותו בקידוד UTF-8.")
    except (zipfile.BadZipFile, PdfReadError):
        st.error("הקובץ פגום או שאינו בפורמט שנבחר.")
    st.stop()


def show_result(agent, result: dict) -> None:
    """Show the result according to the action the agent chose."""
    action = result["action"]

    if action == agent.GENERATE_QUESTIONS:
        st.success("החומר מתאים – הנה 5 שאלות לתרגול:")
        for number, question in enumerate(result["questions"], start=1):
            difficulty = DIFFICULTY_LABELS.get(question["difficulty"], question["difficulty"])
            st.markdown(f"**{number}. {question['question']}**  \nרמת קושי: {difficulty}")
            with st.expander("הצג תשובה"):
                st.markdown(f"**תשובה:** {question['answer']}")
                st.markdown(f"**הסבר:** {question['explanation']}")
    elif action == agent.REQUEST_MORE_MATERIAL:
        st.warning(f"חסר חומר: {result['message']}")
    else:
        st.error(f"לא ניתן להמשיך: {result['message']}")

    with st.expander("JSON מלא"):
        st.json(result)


st.set_page_config(page_title="Study Buddy", page_icon="📚")
st.markdown(RTL_CSS, unsafe_allow_html=True)
st.title("📚 Study Buddy")

version = st.radio("גרסה:", list(VERSIONS), horizontal=True)
study_text = read_study_material().strip()

if st.button("צור שאלות", type="primary"):
    if not study_text:
        st.warning("יש להעלות קובץ או להדביק טקסט.")
        st.stop()

    agent = VERSIONS[version]
    with st.spinner("הסוכן מנתח את החומר..."):
        try:
            result = agent.run_agent(study_text)
        except agent.StudyBuddyError as error:
            st.error(f"שגיאה: {error}")
            st.stop()
    show_result(agent, result)
