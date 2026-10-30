"""
- Renders/Prepares HTML report from resume analysis data
"""
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from typing import Dict

#Uses the templates folder - 4 html files
# 1. action_items.html
# 2. jd_comparison.html
# 3. quick_actions.html
# 4. summary.html 

#builds path to backend's templates folder
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def format_date(value, fmt='%B %d, %Y at %I:%M %p'):
    #Convert ISO timestamp string → human-readable date string. 
    #if empty value return empty string 
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime(fmt)
    except Exception:
        return value

env.filters['format_date'] = format_date

#Extrats from the analysis data and prepares for the templates
def generate_html_reports(analysis_data: Dict) -> Dict[str, str]:
    # 1. Extract timestamp 
    now = datetime.now().isoformat()

    # 2.Overall score + interpretation 
    overall_score = analysis_data.get('ATS_score', 0) or analysis_data.get('ats_score', 0)
    interpretation = analysis_data.get('interpretation') or ''  
    #component scores
    cs = analysis_data.get('component_scores') or {}
    #if scores from pydantic style object convert to dict
    if hasattr(cs, '__dict__'):      # handle Pydantic model objects
        cs = cs.__dict__

    component_scores = {
        'formatting':       float(cs.get('formatting', 0)),
        'keywords':         float(cs.get('keywords', 0)),
        'content':          float(cs.get('content', 0)),
        'skill_validation': float(cs.get('skill_validation', 0)),
        'ats_compatibility': float(cs.get('ats_compatibility', 0)),
    }

    # Progress-bar percentages (used in Report 1's visual breakdown)
    def pct(score, max_score):
        return min(100, max(0, round(score / max_score * 100)))

    #turns into a % for progress bars
    component_pct = {
        'formatting':       pct(component_scores['formatting'],       20),
        'keywords':         pct(component_scores['keywords'],         25),
        'content':          pct(component_scores['content'],          25),
        'skill_validation': pct(component_scores['skill_validation'], 15),
        'ats_compatibility': pct(component_scores['ats_compatibility'], 15),
    }

    raw_feedback = analysis_data.get('detailed_feedback', [])

    #normalise to dictionary
    def to_dict(item):
        if isinstance(item, dict):
            return item
        return item.model_dump() if hasattr(item, 'model_dump') else item.__dict__

    
    # Normalise: each item may be a dict or an IssueDetail Pydantic object
    detailed_feedback = [to_dict(fb) for fb in raw_feedback]

    #Sorts into high,mediumn and low groups based on severity_level
    high_priority   = [fb for fb in detailed_feedback
                       if fb.get('severity_level', '').lower() in ('high',)]
    
    medium_priority = [fb for fb in detailed_feedback
                       if fb.get('severity_level', '').lower() in ('moderate', 'medium')]
    
    low_priority    = [fb for fb in detailed_feedback
                       if fb.get('severity_level', '').lower() in ('low', 'info')]

    #Gather strengths
    strengths = analysis_data.get('strengths', [])

    #Gather skill validation 
    svd_raw = analysis_data.get('skill_validation_details') or {}
    
    if hasattr(svd_raw, 'model_dump'):
        svd_raw = svd_raw.model_dump()

    #populate the validated and unvalidated skill lists, totals, validation %
    validated_skills   = svd_raw.get('validated', [])    # [{'skill', 'projects'}]
    unvalidated_skills = svd_raw.get('unvalidated', [])  # ['Flask', ...]
    total_skills       = svd_raw.get('total', len(validated_skills) + len(unvalidated_skills))
    validated_count    = svd_raw.get('validated_count', len(validated_skills))
    validation_pct     = svd_raw.get('validation_pct', 0.0)

    #7. JD comparison (for Report 3) 
    jd_raw = analysis_data.get('jd_match_analysis') or analysis_data.get('jd_comparison')
    if hasattr(jd_raw, 'model_dump'):
        jd_raw = jd_raw.model_dump()


    #8. Score colour (green / orange / red) 
    if overall_score >= 80:
        score_color = '#16a34a'   # green
        score_color_class = 'score-green'
    elif overall_score >= 60:
        score_color = '#d97706'   # amber
        score_color_class = 'score-amber'
    else:
        score_color = '#dc2626'   # red
        score_color_class = 'score-red'

    #9. Build shared context dict passed to every template 
    context = {
        'timestamp':          now,
        'overall_score':      overall_score,
        'score_color':        score_color,
        'score_color_class':  score_color_class,
        'interpretation':     interpretation,
        'component_scores':   component_scores,
        'component_pct':      component_pct,
        'strengths':          strengths,
        'high_priority':      high_priority,
        'medium_priority':    medium_priority,
        'low_priority':       low_priority,
        'all_feedback':       detailed_feedback,
        # Skill validation
        'validated_skills':   validated_skills,
        'unvalidated_skills': unvalidated_skills,
        'total_skills':       total_skills,
        'validated_count':    validated_count,
        'validation_pct':     validation_pct,
        # JD analysis
        'jd_analysis':        jd_raw,
    }

    #Returns rendered HTML strings in a dictionary
    return {
        'summary':         env.get_template('summary.html').render(**context),
        'skill_report':    env.get_template('action_items.html').render(**context),
        'jd_report':       env.get_template('quick_actions.html').render(**context),
        'recommendations': env.get_template('jd_comparison.html').render(**context),
    }