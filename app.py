import os
import json
import time
import fitz  # PyMuPDF
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Streamlit Page Config - Modern Minimal Layout
st.set_page_config(
    page_title="Smart ATS Resume Matcher",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for UI refinement and card styling
st.markdown("""
    <style>
        /* Modern padding adjustments */
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        
        /* Metric container styling */
        div[data-testid="stMetricValue"] { font-size: 2.2rem; font-weight: 700; }
        
        /* Skill tag pill styling */
        .skill-pill {
            display: inline-block;
            padding: 4px 12px;
            margin: 3px;
            border-radius: 16px;
            font-size: 0.88rem;
            font-weight: 500;
        }
        .skill-match { background-color: #e6f4ea; color: #137333; border: 1px solid #ceead6; }
        .skill-missing { background-color: #fce8e6; color: #c5221f; border: 1px solid #fad2cf; }
    </style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 1. Structured Output Schema Definition
# ------------------------------------------------------------------------------
class ATSAnalysisResult(BaseModel):
    """Pydantic schema enforcing structured JSON output from Gemini."""
    match_percentage: int = Field(
        ..., 
        description="Match score between 0 and 100 based on qualification alignment."
    )
    matching_skills: list[str] = Field(
        ..., 
        description="Key technical and soft skills present in both the resume and job description."
    )
    missing_skills: list[str] = Field(
        ..., 
        description="Crucial skills or keywords present in job description but missing from resume."
    )
    improvements: list[str] = Field(
        ..., 
        description="Exactly 3 high-impact, specific, actionable bullet points to improve the resume."
    )


# ------------------------------------------------------------------------------
# 2. Core Business Logic
# ------------------------------------------------------------------------------
def extract_text_from_pdf(uploaded_file) -> str:
    """Extracts raw text from uploaded PDF using PyMuPDF in-memory."""
    text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text.strip()


def get_available_gemini_models(client: genai.Client) -> list[str]:
    """Dynamically fetches active generation models from Gemini API."""
    try:
        available_models = []
        for model in client.models.list():
            model_id = model.name.replace("models/", "")
            if "gemini" in model_id and "embed" not in model_id and "imagen" not in model_id:
                available_models.append(model_id)

        flash_models = [m for m in available_models if "flash" in m]
        other_models = [m for m in available_models if "flash" not in m]
        
        sorted_models = flash_models + other_models
        return sorted_models if sorted_models else ["gemini-2.5-flash", "gemini-2.0-flash"]
    except Exception:
        return ["gemini-2.5-flash", "gemini-2.0-flash"]


def analyze_resume_with_gemini(resume_text: str, job_description: str) -> tuple[ATSAnalysisResult, str]:
    """Executes ATS analysis with dynamic model discovery and fallback retry logic."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing in environment variables.")

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an expert Applicant Tracking System (ATS) auditor and senior recruiter. "
        "Analyze the resume against the job description with extreme precision. "
        "Provide accurate skill extractions and exactly 3 high-impact, actionable resume recommendations."
    )

    prompt = f"""
    Evaluate this candidate resume against the target job description.

    --- JOB DESCRIPTION ---
    {job_description}

    --- CANDIDATE RESUME ---
    {resume_text}
    """

    models_to_try = get_available_gemini_models(client)
    last_exception = None

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=ATSAnalysisResult,
                        temperature=0.2,
                    )
                )
                data = json.loads(response.text)
                return ATSAnalysisResult(**data), model_name
            except Exception as e:
                last_exception = e
                error_str = str(e).upper()
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    time.sleep(2 * (attempt + 1))
                    continue
                else:
                    break

    raise RuntimeError(f"Analysis failed across endpoints. Details: {last_exception}")


# ------------------------------------------------------------------------------
# 3. Streamlit UI
# ------------------------------------------------------------------------------
def main():
    st.title("Smart Resume Matcher")
    st.text("Upload a candidate resume and job description to evaluate ATS alignment and key skill gaps.")
    st.divider()

    col_input1, col_input2 = st.columns(2, gap="large")

    with col_input1:
        st.markdown("##### Candidate Resume")
        uploaded_pdf = st.file_uploader("Upload PDF file", type=["pdf"], label_visibility="collapsed")

    with col_input2:
        st.markdown("##### Target Job Description")
        job_description = st.text_area(
            "Paste Job Description", 
            height=180, 
            placeholder="Paste role requirements, qualifications, and core duties...",
            label_visibility="collapsed"
        )

    st.write("")
    analyze_btn = st.button("Analyze Alignment", type="primary", use_container_width=True)

    if analyze_btn:
        if not uploaded_pdf:
            st.warning("Please upload a PDF resume.")
            return
        if not job_description.strip():
            st.warning("Please paste a target job description.")
            return

        try:
            with st.status("Analyzing document alignment...", expanded=True) as status:
                st.write("Extracting PDF text content...")
                resume_text = extract_text_from_pdf(uploaded_pdf)
                
                if not resume_text:
                    status.update(label="PDF extraction failed.", state="error")
                    st.error("No readable text found in PDF. Ensure it is not an image scan.")
                    return

                st.write("Querying Gemini ATS model...")
                # Correctly unpack both return values: the analysis Pydantic object AND the model string
                analysis, model_used = analyze_resume_with_gemini(resume_text, job_description)
                status.update(label=f"Analysis completed using {model_used}", state="complete")

            st.write("")

            # 1. Top Section: Metrics Dashboard
            score = analysis.match_percentage
            
            if score >= 80:
                score_color, fit_label = "🟢", "High Match"
            elif score >= 60:
                score_color, fit_label = "🟡", "Moderate Match"
            else:
                score_color, fit_label = "🔴", "Low Match"

            m1, m2 = st.columns([1, 2], gap="medium")
            with m1:
                st.metric(label="ATS Score", value=f"{score}%", delta=fit_label, delta_color="normal")
            with m2:
                st.write("**Overall Alignment**")
                st.progress(score / 100)
                st.caption(f"{score_color} **Fit Rating:** {fit_label} alignment with core requirements.")

            st.divider()

            # 2. Middle Section: Side-by-Side Skills Cards
            s_col1, s_col2 = st.columns(2, gap="large")

            with s_col1:
                st.markdown("### Matching Skills")
                if analysis.matching_skills:
                    pills_html = "".join([f'<span class="skill-pill skill-match">{skill}</span>' for skill in analysis.matching_skills])
                    st.markdown(pills_html, unsafe_allow_html=True)
                else:
                    st.info("No explicit overlapping skills detected.")

            with s_col2:
                st.markdown("### Missing Keywords")
                if analysis.missing_skills:
                    pills_html = "".join([f'<span class="skill-pill skill-missing">{skill}</span>' for skill in analysis.missing_skills])
                    st.markdown(pills_html, unsafe_allow_html=True)
                else:
                    st.info("No major missing required skills.")

            st.divider()

            # 3. Bottom Section: Actionable Recommendations
            st.markdown("### Recommended Action Points")
            for idx, item in enumerate(analysis.improvements, 1):
                with st.container(border=True):
                    st.markdown(f"**{idx}.** {item}")

        except Exception as e:
            st.error(f"Error during execution: {str(e)}")


if __name__ == "__main__":
    main()