# --- 1. LOAD ENVIRONMENT VARIABLES FIRST ---
from dotenv import load_dotenv
load_dotenv()

# --- 2. NOW, IMPORT ALL OTHER LIBRARIES ---
import streamlit as st
import os
import requests
import google.generativeai as genai
from bs4 import BeautifulSoup
from pypdf import PdfReader
import docx
'''from datasets import load_dataset
from kaggle.api.kaggle_api_extended import KaggleApi'''
import pandas as pd

# --- CONSTANTS ---
GEMINI_MODEL_NAME = 'models/gemini-2.0-flash'

# --- Backend Helper Functions ---
def get_pdf_text(pdf_doc):
    """Extracts text from an uploaded PDF file."""
    text = ""
    pdf_reader = PdfReader(pdf_doc)
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def get_docx_text(docx_doc):
    """Extracts text from an uploaded Word document."""
    doc = docx.Document(docx_doc)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_skills_from_resume(resume_text):
    """Uses the Gemini model to extract key skills from the resume text."""
    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        prompt = f"""
You are an expert HR analyst. Analyze the following resume text and extract the top 5 most important technical skills and top 3 soft skills.
Return the skills as a single, comma-separated list. For example: Python,Java,SQL,Communication,Teamwork

Resume Text:\n---\n{resume_text}\n---\nSkills:
"""
        response = model.generate_content(prompt)
        skills_text = response.text.strip()
        if not skills_text:
            return []
        return [skill.strip() for skill in skills_text.split(',')]
    except Exception as e:
        st.error(f"Error during resume analysis: {e}")
        st.info("The AI model could not be reached. Please check your API key and project setup.")
        return None

# --- MULTI-SOURCE SCRAPERS ---
def scrape_from_geeksforgeeks(skill):
    try:
        sanitized_skill = skill.replace(' ', '-').lower()
        url = f"https://www.geeksforgeeks.org/{sanitized_skill}-interview-questions/"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        questions = soup.select('div.entry-content ol > li > p, div.entry-content ol > li > strong')
        question_texts = [q.get_text(strip=True) for q in questions[:5]]
        return (question_texts, url) if question_texts else None
    except requests.exceptions.RequestException:
        return None

def scrape_from_interviewbit(skill):
    try:
        sanitized_skill = skill.replace(' ', '-').lower()
        url = f"https://www.interviewbit.com/technical-interview-questions/{sanitized_skill}/"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        questions = soup.select('div.problem-title')
        question_texts = [q.get_text(strip=True) for q in questions[:5]]
        return (question_texts, url) if question_texts else None
    except requests.exceptions.RequestException:
        return None

def scrape_all_technical_questions(skill):
    print(f"Attempting to scrape questions for: {skill}")
    scrapers = [scrape_from_geeksforgeeks, scrape_from_interviewbit]
    for scraper_func in scrapers:
        result = scraper_func(skill)
        if result:
            print(f"Success with {scraper_func.__name__}")
            return result
    print(f"All scrapers failed for: {skill}")
    return None

def scrape_behavioral_questions():
    try:
        url = "https://www.themuse.com/advice/behavioral-interview-questions-answers-examples"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        questions = soup.select('div.article-body-container h2')
        question_texts = [q.get_text(strip=True) for q in questions[:7]]
        return (question_texts, url) if question_texts else None
    except requests.exceptions.RequestException:
        return None

# --- HUGGING FACE + KAGGLE DATASETS ---
@st.cache_data
def load_external_dataset():
    """
    Loads interview question datasets from Hugging Face and Kaggle.
    This function is cached to avoid re-downloading on every script run.
    """
    question_data = {}
    # --- HUGGING FACE DATASET ---
    try:
        hf_token = os.getenv("HUGGINGFACE_API_KEY")
        dataset = load_dataset("aniruddha/interview-questions-dataset", token=hf_token)
        for row in dataset["train"]:
            skill = row.get("skill", "").lower().strip()
            question = row.get("question", "").strip()
            if skill and question:
                question_data.setdefault(skill, []).append(question)
        print("✅ Loaded dataset from Hugging Face")
    except Exception as e:
        print(f"⚠️ Could not load Hugging Face dataset: {e}")
    # --- KAGGLE DATASET ---
    try:
        api = KaggleApi()
        api.authenticate()
        print("✅ Kaggle API authenticated successfully!")
        dataset_name = "tanmay111999/interview-questions-dataset"
        data_path = "data/"
        os.makedirs(data_path, exist_ok=True)
        api.dataset_download_files(dataset_name, path=data_path, unzip=True)
        for file in os.listdir(data_path):
            if file.endswith(".csv"):
                df = pd.read_csv(os.path.join(data_path, file))
                for _, row in df.iterrows():
                    skill = str(row.get("skill", "")).lower().strip()
                    question = str(row.get("question", "")).strip()
                    if skill and question:
                        question_data.setdefault(skill, []).append(question)
                print(f"✅ Kaggle dataset loaded successfully: {file}")
                break
    except Exception as e:
        print(f"⚠️ Could not load Kaggle dataset: {e}")
    # --- Fallback Dataset ---
    if not question_data:
        question_data = {
            'python': ["What are Python decorators?", "Explain difference between list and tuple."],
            'java': ["Explain OOP concepts in Java.", "Difference between JDK and JRE?"],
            'sql': ["What is a primary key?", "Explain joins in SQL."]
        }
        print("⚠️ Using fallback questions (local static).")
    return question_data

BACKUP_QUESTIONS = load_external_dataset()

# --- MAIN STREAMLIT APP ---
def main():
    st.set_page_config(page_title="AI Resume Analyzer", layout="wide")
    st.title("AI-Powered Resume Analyzer & Interview Prep Chatbot")

    if not os.getenv("GOOGLE_API_KEY"):
        st.error("GOOGLE_API_KEY not found. Please create a .env file and add it.")
        st.stop()
    try:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    except Exception as e:
        st.error(f"Failed to configure Google AI: {e}")
        st.stop()
    if "chat_session" not in st.session_state:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        st.session_state.chat_session = model.start_chat(history=[])

    # --- Sidebar ---
    with st.sidebar:
        st.header("Controls")
        uploaded_file = st.file_uploader("Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])
        if st.button("Analyze Resume", use_container_width=True, disabled=not uploaded_file):
            with st.spinner("Analyzing resume and preparing questions..."):
                resume_text = get_pdf_text(uploaded_file) if uploaded_file.name.endswith('.pdf') else get_docx_text(uploaded_file)
                extracted_skills = extract_skills_from_resume(resume_text)
                if extracted_skills is not None:
                    st.session_state.skills = extracted_skills
                    st.session_state.resume_text = resume_text # Store resume text
                    prepared_questions = {}
                    failed_skills = []
                    for skill in extracted_skills:
                        skill_lower = skill.lower()
                        if skill_lower in BACKUP_QUESTIONS:
                            questions = BACKUP_QUESTIONS[skill_lower][:5]
                            prepared_questions[skill] = (questions, "Loaded from Dataset")
                        else:
                            result = scrape_all_technical_questions(skill)
                            if result:
                                prepared_questions[skill] = result
                            else:
                                failed_skills.append(skill)
                    st.session_state.behavioral_questions = scrape_behavioral_questions()
                    st.session_state.prepared_questions = prepared_questions
                    st.session_state.failed_skills = failed_skills
                    st.session_state.resume_analyzed = True
                    
                    # --- NEW: CONTEXT-AWARE CHAT INITIALIZATION ---
                    skills_str = ", ".join(st.session_state.skills)
                    
                    # This is the first message the user will see from the bot.
                    initial_model_message = f"Hello! I've analyzed your resume and identified these key skills: **{skills_str}**.\n\nI'm ready to help you prepare. You can ask me for more interview questions for these skills or for feedback on your answers. How would you like to start?"

                    # Start a new chat session with this context
                    model = genai.GenerativeModel(GEMINI_MODEL_NAME)
                    
                    # The history now starts with the model's helpful message
                    st.session_state.chat_session = model.start_chat(history=[
                        {'role': 'model', 'parts': [initial_model_message]}
                    ])
                    st.rerun()

        if st.button("New Chat", use_container_width=True):
            model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.resume_analyzed = False
            st.session_state.skills = []
            st.session_state.prepared_questions = {}
            st.rerun()

    # --- MAIN CHAT AND RESULTS AREA ---
    if st.session_state.get("resume_analyzed"):
        st.subheader("Resume Analysis Results")
        if "skills" in st.session_state and st.session_state.skills:
            st.write("Top Skills Identified:", ", ".join(f"`{s}`" for s in st.session_state.skills))
        if "prepared_questions" in st.session_state and st.session_state.prepared_questions:
            with st.expander("Show Initial Technical Questions", expanded=True):
                for skill, (questions, source) in st.session_state.prepared_questions.items():
                    st.markdown(f"**Questions for {skill.title()}** (Source: {source})")
                    for q in questions:
                        st.markdown(f"- {q}")
        if "behavioral_questions" in st.session_state and st.session_state.behavioral_questions:
            questions, url = st.session_state.behavioral_questions
            with st.expander("Show Initial Behavioral Questions", expanded=True):
                 st.markdown(f"**Common Questions** (Source: [Link]({url}))")
                 for q in questions:
                     st.markdown(f"- {q}")
        st.divider()

    # Display chat history
    for message in st.session_state.chat_session.history:
        # Don't display the initial system instruction to the user
        with st.chat_message(name=message.role):
            st.markdown(message.parts[0].text)

    # Get user input
    user_prompt = st.chat_input("Ask for more questions or for feedback on your answers...")
    if user_prompt:
        # --- NEW: ADD CONTEXT TO USER'S PROMPT ---
        # This ensures the model *always* knows the skills to focus on
        skills_context = f"Based on the resume skills: {', '.join(st.session_state.get('skills', []))}, answer the following prompt: {user_prompt}"
        
        st.chat_message("user").markdown(user_prompt)
        gemini_response = st.session_state.chat_session.send_message(skills_context)
        with st.chat_message("model"):
            st.markdown(gemini_response.text)

if __name__ == "__main__":

    main()
