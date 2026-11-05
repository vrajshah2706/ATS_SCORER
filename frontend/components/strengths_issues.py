"""
component for displaying strengths and critical issues in the resume analysis
"""
from typing import Any, Dict, List
import streamlit as st

#Display a bulleted list of strengths, or a message if the list is empty.
def display_strengths(strengths: List[str]) -> None:
    st.markdown("### 💪 Strengths")
    if not strengths:
        st.info("Keep improving your resume to unlock strengths!")
        return
    for item in strengths:
        st.markdown(f"- {item}")

#Display a bulleted list of critical issues, or a message if the list is empty.
def display_critical_issues(analysis: Dict[str, Any]) -> None:
    #get fields
    critical = analysis.get("critical_issues") or []
    summary = analysis.get("issues_summary") or []

    if not critical and not summary:
        st.success("### ✅ No Critical Issues Found!")
        st.markdown("Your resume doesn't have any urgent issues. Nice work.")
        return

    #Everything flagged that is not critical (shown in an expandable list)
    extra = [s for s in summary if s not in critical]

    if critical:
        #Only show the red banner when something is actually critical
        st.markdown("### 🚨 Critical Issues")
        st.error("These issues should be addressed first for better ATS performance.")
        for item in critical:
            st.markdown(f"- {item}")
    else:
        #Issues were found, but none are critical
        st.markdown("### ✅ No Critical Issues")
        st.success("Nothing here will block your resume outright, but there are improvements worth making.")

    #Non-critical issues: open by default when there are no critical ones, so they are not hidden
    if extra:
        label = "📋 Additional flagged items" if critical else f"📋 Improvements to consider ({len(extra)})"
        with st.expander(label, expanded=not critical):
            for item in extra:
                st.markdown(f"- {item}")