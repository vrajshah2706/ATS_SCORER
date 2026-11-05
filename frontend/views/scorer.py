"""
- Builds resume scoring page
- Handles:
    upload form 
    send the resume to the backend
    display the results 
    provides download options
"""
from typing import Optional

import requests
import streamlit as st

from frontend.services import api_client
from frontend.components.dashboard import display_results_dashboard

#Prepares the JD for analysis
def _read_jd(jd_file, jd_text: str) -> str:
    """
    Turn whatever the user provided into a plain JD string for the backend.

    For .txt files we decode in-process — that's a trivial operation, no need
    for a backend round-trip. For PDF/DOCX, we'd need the backend's parser;
    we don't have a public endpoint for that, so we ask the user to paste text
    instead for non-txt JDs.
    """
    if jd_text:
        return jd_text.strip()
    if jd_file is None:
        return ""
    if jd_file.name.lower().endswith(".txt"):
        return jd_file.getvalue().decode("utf-8", errors="ignore")
    st.warning(
        "Job description files must be `.txt` for now — paste the JD text instead "
        "if you have a PDF or DOCX."
    )
    return ""

#Turns types of errors into user facing messages
def _show_backend_error(exc: Exception) -> None:

    if isinstance(exc, requests.ConnectionError):
        st.error("Could not reach the backend. Is `uvicorn backend.main:app` running? (see the README for the port and start command)")
    elif isinstance(exc, requests.Timeout):
        st.error("The backend took too long to respond. Try a smaller resume or check the server logs.")
    elif isinstance(exc, requests.HTTPError) and exc.response is not None:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        st.error(f"Backend returned {exc.response.status_code}: {detail}")
    else:
        st.error(f"Unexpected error: {exc}")

#Creates plain text summary from the score, stregths, critical issues & suggestions
def _summary_text(analysis: dict) -> str:

    score = analysis.get("ATS_score", analysis.get("ats_score", 0))
    lines = [f"ATS Score: {score:.0f}/100", ""]
    if analysis.get("strengths"):
        lines.append("STRENGTHS:")
        lines.extend(f"  - {s}" for s in analysis["strengths"])
        lines.append("")
    if analysis.get("critical_issues"):
        lines.append("CRITICAL ISSUES:")
        lines.extend(f"  - {s}" for s in analysis["critical_issues"])
        lines.append("")
    if analysis.get("suggestions"):
        lines.append("SUGGESTIONS:")
        lines.extend(f"  - {s}" for s in analysis["suggestions"])
    return "\n".join(lines)

#Shows resume uploaded and when JD comparison is selcted
def _render_upload_area(analysis_mode: str):
    """Two-column upload widgets. Returns (resume_file, jd_file, jd_text)."""
    left, right = st.columns(2)

    #Upload Resume file
    with left:
        st.markdown("### 📄 Upload Resume")
        resume_file = st.file_uploader(
            "Choose your resume file",
            type=["pdf", "doc", "docx"],
            help="Supported: PDF, DOC, DOCX (max 5 MB)",
            key="resume_upload",
        )
        if resume_file:
            st.success(f"✅ {resume_file.name} ({resume_file.size / 1024:.1f} KB)")

    #Upload JD file or paste text if JD comparison is selected
    jd_file: Optional[object] = None
    jd_text = ""

    with right:
        if analysis_mode == "Job Description Comparison":
            st.markdown("### 📋 Job Description")
            jd_method = st.radio(
                "Input method:",
                ["Paste Text", "Upload .txt File"],
                horizontal=True,
                key="jd_input_method",
            )
            if jd_method == "Upload .txt File":
                jd_file = st.file_uploader(
                    "Choose JD file (.txt only)",
                    type=["txt"],
                    key="jd_upload",
                )
                if jd_file:
                    st.success(f"✅ {jd_file.name}")
            else:
                jd_text = st.text_area(
                    "Paste job description text:",
                    height=200,
                    placeholder="Paste the JD here...",
                    key="jd_text",
                )
                if jd_text:
                    st.success(f"✅ {len(jd_text)} characters")
        else:
            st.markdown("### 📋 Job Description")
            st.info("Switch to 'Job Description Comparison' mode to enable JD matching.")

    return resume_file, jd_file, jd_text

#Lets user download the PDF report and summary text file
def _render_export_buttons(analysis: dict) -> None:
    st.markdown("### 📥 Export Results")
    c1, c2 = st.columns(2)

    with c1:
        # Lazy: only call the backend the first time the user clicks expand.
        if st.button("📑 Generate PDF Report", use_container_width=True, type="primary"):
            try:
                with st.spinner("Generating PDF on backend..."):
                    #Calling backend API to generate PDF report
                    pdf_bytes = api_client.generate_pdf(
                        analysis,
                        access_token=st.session_state["access_token"],
                    )
                #Store the PDF bytes in session state so we don't have to call 
                # the backend again if the user clicks the button again
                st.session_state["scorer_pdf_bytes"] = pdf_bytes
            except requests.RequestException as exc:
                _show_backend_error(exc)

        # If we have PDF bytes in session state, show the download button
        if "scorer_pdf_bytes" in st.session_state:
            st.download_button(
                "⬇️ Download PDF",
                data=st.session_state["scorer_pdf_bytes"],
                file_name="ats_resume_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf_report",
            )
    # If we have analysis results, show the summary text download button
    with c2:
        st.download_button(
            "📄 Download Summary (.txt)",
            data=_summary_text(analysis),
            file_name="ats_summary.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_summary",
        )

#Page flow
def render() -> None:
    st.title("🎯 ATS Resume Scorer")
    st.markdown("Upload your resume — and optionally a job description — for a comprehensive analysis.")

    #Sidebar info of two analysis modes
    with st.sidebar:
        st.markdown("---")
        st.markdown("## 📊 Analysis Options")
        st.info(
            "**General ATS Score**: resume only — overall compatibility.\n\n"
            "**JD Comparison**: resume + job description — targeted match analysis."
        )

    st.markdown("---")

    #Shows model selector 
    analysis_mode = st.radio(
        "Select Analysis Mode:",
        ["General ATS Score", "Job Description Comparison"],
        horizontal=True,
    )

    st.markdown("---")

    #Show upload area
    resume_file, jd_file, jd_text = _render_upload_area(analysis_mode)

    st.markdown("---")

    #If no resume, ask user to upload one and if we have a prior result in session, render it again.
    if not resume_file:
        st.info("👆 Upload your resume to begin.")
        # If we have a prior result in session, render it again.
        if st.session_state.get("scorer_analysis"):
            display_results_dashboard(st.session_state["scorer_analysis"])
        return

    #User must be signed in 
    access_token = st.session_state.get("access_token")
    if not access_token:
        st.warning("⚠️ Sign in from the sidebar to analyze a resume.")
        return

    _, mid, _ = st.columns([1, 2, 1])
    
    #Analyze button in the middle column
    with mid:
        analyze = st.button("🚀 Analyze Resume", use_container_width=True, type="primary")

    # If user doesn't click analyze, we check if we have a prior result in session and render it again.
    if not analyze:
        # Re-show previous result on rerun (e.g. after PDF generation).
        if st.session_state.get("scorer_analysis"):
            display_results_dashboard(st.session_state["scorer_analysis"])
            _render_export_buttons(st.session_state["scorer_analysis"])
        return

    # Fresh analysis — drop any cached PDF/result.
    st.session_state.pop("scorer_pdf_bytes", None)
    st.session_state.pop("scorer_analysis", None)

    #Prepares JD
    job_description = _read_jd(jd_file, jd_text) if analysis_mode == "Job Description Comparison" else ""

    try:
        with st.spinner("Analyzing your resume... this can take 10–30 seconds."):
            #Calling backend API
            analysis = api_client.analyse_resume(
                resume_file=resume_file,
                access_token=access_token,
                job_description=job_description,
            )
    except requests.RequestException as exc:
        _show_backend_error(exc)
        return

    #On success, store the analysis in session state and 
    #display the results dashboard and export buttons
    st.session_state["scorer_analysis"] = analysis
    st.success("✅ Analysis complete!")
    display_results_dashboard(analysis)
    _render_export_buttons(analysis)