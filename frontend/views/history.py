"""
Implements Streamlit page that displays a signed in user's past resume analyses
"""
import requests
import streamlit as st
from datetime import datetime

from frontend.services import api_client


#Turns the database timestamp (UTC, ISO format) into a readable date in the computer's local time zone.
#If it cannot be parsed, the original text is shown unchanged.
def _format_timestamp(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone().strftime("%d %b %Y, %I:%M %p")
    except (ValueError, AttributeError):
        return raw


#Display a different message depending on th type of error.
def _show_backend_error(exc: Exception) -> None:
    if isinstance(exc, requests.ConnectionError):
        st.error("Could not reach the backend. Is it running? (see the README for how to start it)")
    elif isinstance(exc, requests.HTTPError) and exc.response is not None:
        st.error(f"Backend returned {exc.response.status_code}: {exc.response.text}")
    else:
        st.error(f"Unexpected error: {exc}")


def render() -> None:
    st.title("📊 Analysis History") #Title of page
    st.markdown("Past analyses saved against your account.")

    #Gets session token
    access_token = st.session_state.get("access_token")
    
    #Check if user is signed in, if not display warning message
    if not access_token:
        st.warning("⚠️ Sign in from the sidebar to view your history.")
        return

    #Loads history from backend, if there is an error display a message
    try:
        history = api_client.get_history(access_token)
    except requests.RequestException as exc:
        _show_backend_error(exc)
        return

    #Handles an empty history, display a message and a button to go to the ATS Scorer page
    if not history:
        st.info("No analyses yet for this account. Run a scoring on the ATS Scorer page first.")
        if st.button("🎯 Go to ATS Scorer"):
            #Offer to navigate
            st.session_state.current_view = "scorer"
            st.rerun() #rerun the app to navigate to the scorer page
        return

    #Shows history
    st.markdown(f"**Total analyses:** {len(history)}")
    st.markdown("---")

    #for each history entry, display the filename, score, and created_at date in an expander.
    # Inside the expander, display the component scores and JD match percentage if available. 
    # Also provide a delete button for each entry.
    for idx, entry in enumerate(history):
        #gets fields
        filename = entry.get("filename", "resume")
        ats_score = float(entry.get("ats_score", 0))
        created_at = _format_timestamp(entry.get("created_at", ""))
        analysis = entry.get("analysis_result", {}) or {}

        component_scores = analysis.get("component_scores", {}) or {}
        jd_comparison = analysis.get("jd_comparison") or analysis.get("jd_match_analysis")

        #Shows in an expander with the filename, score, and created_at date
        with st.expander(f"📄 {filename} — Score: {ats_score:.0f}/100 — {created_at}"):
            #Shows the component scores in three columns, with the overall score within each
            # expander. If JD comparison is available, show the match percentage as well.
        
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Overall", f"{ats_score:.0f}/100")
                st.metric("Formatting", f"{component_scores.get('formatting', 0):.0f}/20")
            with c2:
                st.metric("Keywords", f"{component_scores.get('keywords', 0):.0f}/25")
                st.metric("Content", f"{component_scores.get('content', 0):.0f}/25")
            with c3:
                st.metric("Skill Validation", f"{component_scores.get('skill_validation', 0):.0f}/15")
                st.metric("ATS Compatibility", f"{component_scores.get('ats_compatibility', 0):.0f}/15")

            if jd_comparison:
                st.markdown(f"**JD Match:** {jd_comparison.get('match_percentage', 0):.0f}%")

            #Penalty subtracted from the five components for missing job description keywords (saved with the analysis)
            jd_penalty = float(analysis.get("jd_penalty") or 0)
            if jd_penalty > 0:
                st.markdown(f"**JD keyword gap:** −{jd_penalty:.0f} points (already included in the overall score)")

            entry_id = entry.get("id")
            #If the entry has an ID, show a delete button. If the user clicks the delete button,
            # call the backend to delete the entry and rerun the app to refresh the history.
            if entry_id:
                if st.button("🗑️ Delete", key=f"delete_{idx}"):
                    try:
                        #Call the backend to delete the entry
                        api_client.delete_history_entry(str(entry_id), access_token)
                        st.success("Deleted.")
                        st.rerun() #refresh
                    except requests.RequestException as exc:
                        _show_backend_error(exc)