"""
- Users will get overwhelmed with all the issues triggered to them at once
- Tell us what issues we have to work on first
- Issues (from feedback engine) are categorise and classified as critical,high,medium and low 
  allowing users to prioritise resume changes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict,List,Optional


############
#  HELPER  #
############
class Priority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    #Priority.CRITICAL

@dataclass
class Recommendation:
    title:str
    description: str
    priority: Priority
    impact_score: float #impacts the sort order (priority)
    category: str
    action_items: List[str]

###################
# RECOMMENDATIONS #
###################

#generatior 1 - skill suggestions
def generate_skill_recommendations(skill_validation_results: Dict) -> List[Recommendation]:
    recommendation = []
    unvalidated = skill_validation_results.get("unvalidated_skills", [])
    validated_pct = skill_validation_results.get("validation_percentage", 0.0)

    #If nothing in unvalidated skills return 
    if not unvalidated:
        return recommendation

    #setting priority and impact based on validated %
    if validated_pct < 0.4:
        priority, impact = Priority.CRITICAL, 8.0
    elif validated_pct < 0.6:
        priority, impact = Priority.HIGH, 6.0
    elif validated_pct < 0.8:
        priority, impact = Priority.MEDIUM, 4.0
    else :
        priority, impact = Priority.LOW, 2.0

    action_items = [
        f"Add a project or experience demonstrating '{skill}', or remove it from skills"
        for skill in unvalidated [:5]
    ]

    #if unvalidated > 5 then just giving count to user
    if len(unvalidated) > 5:
        action_items.append(f"... and {len(unvalidated) - 5} more unvalidated skill(s)")

    #Appending to recommendation array
    recommendation.append(Recommendation(
        title= "Validate Your Listed Skills",
        description= (
            f"{len(unvalidated)} skill(s) are not demonstrated in your projects or experience."
            "ATS systems and recruiters look for evidence that you've actually used the skills you claim"
        ),
        priority= priority,
        impact_score=impact,
        category="skill_validation",
        action_items=action_items,
    ))

    return recommendation

#generator 2 - grammar suggestions
def generate_grammar_recommendations(grammar_results: Dict) -> List[Recommendation]:
    recommendations = []

    critical_errors = grammar_results.get("critical_errors", [])
    moderate_errors = grammar_results.get("moderate_errors", [])
    minor_errors = grammar_results.get("minor_errors", [])

    total = len(critical_errors) + len(moderate_errors) + len(minor_errors)

    #No errors return 
    if total == 0:
        return recommendations

    #for critical errors
    if critical_errors:
        action_items = []
        #top 5
        for error in critical_errors[:5]:
            word = error.get("error_text", "unknown")
            suggest = error.get("suggestions", [])
            suffix = f" -> '{suggest[0]}'" if suggest else ''
            action_items.append(f"Fix '{word}'{suffix}: {error.get("message", "")}")

        #additonal errors just giving them count 
        if len(critical_errors) > 5:
            action_items.append(f"... and {len(critical_errors) - 5} more critical error(s)")

        recommendations.append(Recommendation(
            title= "Fix Critical Spelling/Grammar Error",
            description= (
                f"{len(critical_errors)} critical error(s) found. These spelling mistakes or"
                "major grammar issues will make your resume look unprofessional."

            ),
            priority=Priority.CRITICAL,
            impact_score= min(10.0 , len(critical_errors) * 2.0),
            category     = 'grammar',
            action_items = action_items
        ))

    #for moderate errors
    if moderate_errors:
        action_items = []
        #top 3 
        for error in moderate_errors[:3]:
            word    = error.get('error_text', 'unknown')
            suggest = error.get('suggestions', [])
            suffix  = f" → '{suggest[0]}'" if suggest else ''
            action_items.append(f"Fix '{word}'{suffix}: {error.get('message', '')}")
        
        #if additonal erros just showing count
        if len(moderate_errors) > 3:
            action_items.append(f'... and {len(moderate_errors) - 3} more moderate error(s)')


        recommendations.append(Recommendation(
            title        = 'Address Punctuation and Capitalization Issues',
            description  = (
                f'{len(moderate_errors)} moderate error(s) found. '
                'These punctuation or capitalization issues should be corrected.'
            ),
            priority     = Priority.HIGH,
            impact_score = min(6.0, len(moderate_errors) * 1.0),
            category     = 'grammar',
            action_items = action_items,
        ))

    #For minor errors and only if >= 3
    if minor_errors and len(minor_errors) >= 3:
        recommendations.append(Recommendation(
            title        = 'Consider Style Improvements',
            description  = (
                f'{len(minor_errors)} minor style suggestion(s) found. '
                'These are optional improvements for better readability.'
            ),
            priority     = Priority.LOW,
            impact_score = 1.0,
            category     = 'grammar',
            action_items = [
                f'Review {len(minor_errors)} style suggestion(s) for improved readability',
                'Use consistent formatting throughout',
            ],
        ))

    return recommendations

#generator 3 - location recommendations
def generate_location_recommendations(location_results: Dict) -> List[Recommendation]:
    recommendations = []
    detected_locations = location_results.get("detected_locations", [])
    privacy_risk = location_results.get("privacy_risk", None)

    #No privacy risk or detected locations then return 
    if privacy_risk == "none" or not detected_locations:
        return recommendations

    addresses = [loc for loc in  detected_locations if loc.get("type") == "address"]
    zip_codes = [loc for loc in detected_locations if loc.get("type") == "zip"]

    action_items = []

    #top 3 address and zip code
    for addr in addresses[:2]:
        action_items.append(f"Remove full address: '{addr.get("text","")}'")
    for z in zip_codes[:2]:
        action_items.append(f"Remove zip code: '{z.get("text", "")}'")
    action_items.append("Kepp only 'City, State' in your contact header")

    # Assigning priority, impact and description base on privacy_risk
    if privacy_risk == "high":
        priority = Priority.CRITICAL
        impact = 5.0
        description = (
            "Your resume contains detailed locations information that poses a privacy risk."
            "Full addresses and zip codes are unnecessary and can be used to identify your location"
        )
    elif privacy_risk == 'medium':
        priority    = Priority.HIGH
        impact      = 3.0
        description = (
            "Your resume contains multiple location mentions. Consider simplifying to just "
            "'City, State' in your contact header."
        )
    else:
        priority    = Priority.MEDIUM
        impact      = 2.0
        description = (
            'Minor location information detected. Consider reviewing for unnecessary location details.'
        )

    recommendations.append(Recommendation(
        title        = 'Protect Your Location Privacy',
        description  = description,
        priority     = priority,
        impact_score = impact,
        category     = 'location',
        action_items = action_items,
    ))
    
    return recommendations

# generator 4 - keywords
#optional because users can upload JD and Resume where its easier to analyse keywords based on JD
#or just resume where we can just give general recommendation 
def generate_keyword_recommendations(
        keyword_analysis: Optional[Dict] = None,
        resume_keywords: Optional[List[str]] = None,
) -> List[Recommendation]:

    recommendations = []

    #for keyword analysis against JD - user uploads resume and JD
    if keyword_analysis:
        missing = keyword_analysis.get("missing_keyword" , [])
        gap = keyword_analysis.get("skills_gap",[])
        match_pct = keyword_analysis.get("match_percentage", 0.0)

        #for missing keywords
        if missing:
            #Settting priority and impact based on match percentage 
            if match_pct < 40:
                priority, impact = Priority.CRITICAL, 8.0
            elif match_pct < 60:
                priority, impact = Priority.HIGH, 6.0
            else:
                priority, impact = Priority.MEDIUM, 4.0

            action_items = [f"Add '{kw}' to your resume in a relevant section" for kw in missing[:7]]
            
            #additional missing keywords, just giving count 
            if len(missing) > 7:
                action_items.append(f'... and {len(missing) - 7} more missing keyword(s)')

            recommendations.append(Recommendation(
                title        = 'Add Missing Job Description Keywords',
                description  = (
                    f'{len(missing)} keyword(s) from the job description are missing from '
                    f'your resume. Your current match is {match_pct:.0f}%.'
                ),
                priority     = priority,
                impact_score = impact,
                category     = 'keywords',
                action_items = action_items,
            ))

        #for skills gap - what skills user might want to add 
        if gap:
            action_items  = [f"Consider adding '{skill}' if you have this skill" for skill in gap[:5]]
            #additional gaps - just giving count 
            if len(gap) > 5:
                action_items.append(f'... and {len(gap) - 5} more skill(s) mentioned in the job')

            recommendations.append(Recommendation(
                title        = 'Address Skills Gap',
                description  = (
                    f'The job description mentions {len(gap)} skill(s) not found in your resume. '
                    'Add these skills if you have them, or consider gaining them.'
                ),
                priority     = Priority.HIGH,
                impact_score = 5.0,
                category     = 'keywords',
                action_items = action_items,
                ))

    #for just resume keywords - user only uploads resume 
    elif resume_keywords is not None:
        #provide recommendation only if keywords are less than 10 
        if len(resume_keywords) < 10:
            recommendations.append(Recommendation(
                title        = 'Increase Keyword Density',
                description  = (
                    f'Your resume contains only {len(resume_keywords)} keywords. '
                    'Adding more relevant keywords will improve ATS matching.'
                ),
                priority     = Priority.MEDIUM,
                impact_score = 4.0,
                category     = 'keywords',
                action_items = [
                    "Add more technical skills and tools you've used",
                    'Include industry-specific terminology',
                    'Mention relevant certifications and methodologies',
                ],
            ))

    return recommendations

# generator 5 - formatting and structure recommendation 
def generate_formatting_recommendations(
        score_results: Dict ,
        sections: Dict[str, str],
) -> List[Recommendation]:
    
    recommendations  = []
    formatting_score = score_results.get('formatting_score', 0.0)

    section_recommendations = {
        'experience': "Add a clear 'Experience' or 'Work History' section",
        'education':  "Add an 'Education' section with your qualifications",
        'skills':     "Add a 'Skills' section listing your technical and soft skills",
        'summary':    "Consider adding a 'Summary' or 'Objective' section at the top",
        'projects':   "Consider adding a 'Projects' section to showcase your work",
    }

    missing_sections = []
    for section_name, suggestion in section_recommendations.items():
        content = sections.get(section_name, '')
        #only adding as missing section if the section is not present or has < 20 words
        if not content or len(content) < 20:
            missing_sections.append((section_name, suggestion))

    #madatory sections 
    core_missing     = [(n, s) for n, s in missing_sections if n in ['experience', 'education', 'skills']]
    #optional sections
    optional_missing = [(n, s) for n, s in missing_sections if n in ['summary', 'projects']]

    #for core section
    if core_missing:
        recommendations.append(Recommendation(
            title        = 'Add Missing Core Sections',
            description  = (
                f'Your resume is missing {len(core_missing)} essential section(s). '
                'ATS systems expect standard resume sections.'
            ),
            priority     = Priority.CRITICAL,
            impact_score = 7.0,
            category     = 'formatting',
            action_items = [suggestion for _, suggestion in core_missing],
        ))

    #for optional section and structure/formatting score less than 15
    if optional_missing and formatting_score < 15:
        recommendations.append(Recommendation(
            title        = 'Consider Adding Optional Sections',
            description  = 'Adding a summary and projects section can strengthen your resume.',
            priority     = Priority.LOW,
            impact_score = 2.0,
            category     = 'formatting',
            action_items = [suggestion for _, suggestion in optional_missing],
        ))

    #for structure/formatting score less than 12 
    if formatting_score < 12:   # Below 60% of 20 pts
        recommendations.append(Recommendation(
            title        = 'Improve Resume Structure',
            description  = (
                f'Your formatting score is {formatting_score:.1f}/20. '
                'Better structure will improve ATS parsing and readability.'
            ),
            priority     = Priority.HIGH,
            impact_score = 5.0,
            category     = 'formatting',
            action_items = [
                'Use bullet points to list achievements and responsibilities',
                'Add clear section headers (Experience, Education, Skills)',
                'Ensure consistent formatting throughout',
                'Use a clean, single-column layout',
            ],
        ))

    return recommendations


################################ 
# PRIORITISING RECOMMENDATION  #
################################
def _prioritise_recommendations(recommendations: List[Recommendation]) -> List[Recommendation]:
    priority_order = {
        Priority.CRITICAL: 0,
        Priority.HIGH: 1,
        Priority.MEDIUM: 2,
        Priority.LOW: 3,
    }

    #using custom tuple key 
    return sorted (
        recommendations,
        #highest impact score will come first and so on 
        #using -r to only reverse within each tier and not the entire tuple
        key=lambda r: (priority_order[r.priority], -r.impact_score) 
       
    )

################
# ORCHESTRATOR #
################
def generate_all_recommendations(
    skill_validation_results: Dict,
    grammar_results: Dict,
    location_results: Dict,
    score_results: Dict,
    sections: Dict[str, str],
    keyword_analysis: Optional[Dict] = None,
    resume_keywords: Optional[List[str]] = None,
) -> Dict:

    #all recommendations
    all_recs = []

    # Collect from all five domain generators
    # extend unpacks the returned list and adds as elements
    all_recs.extend(generate_skill_recommendations(skill_validation_results))
    all_recs.extend(generate_grammar_recommendations(grammar_results))
    all_recs.extend(generate_location_recommendations(location_results))
    all_recs.extend(generate_keyword_recommendations(keyword_analysis, resume_keywords))
    all_recs.extend(generate_formatting_recommendations(score_results, sections))

    #Sort: critical first, highest impact within each tier
    prioritized = _prioritise_recommendations(all_recs)

    #Group by priority level for convenient access
    critical = [r for r in prioritized if r.priority == Priority.CRITICAL]
    high     = [r for r in prioritized if r.priority == Priority.HIGH]
    medium   = [r for r in prioritized if r.priority == Priority.MEDIUM]
    low      = [r for r in prioritized if r.priority == Priority.LOW]

    # Estimate improvement potential (sum of impact scores, capped at 30)
    estimated_improvement = min(30.0, sum(r.impact_score for r in prioritized))

    return {
        'all_recommendations':      prioritized,
        'critical_recommendations': critical,
        'high_recommendations':     high,
        'medium_recommendations':   medium,
        'low_recommendations':      low,
        'total_count':              len(prioritized),
        'estimated_improvement':    estimated_improvement,
    }

#converting recommendation into json to be passed through API
def format_recommendations_for_api(recommendations_result: Dict) -> List[Dict]:
    priority_icons = {
        Priority.CRITICAL: '🔴',
        Priority.HIGH:     '🟠',
        Priority.MEDIUM:   '🟡',
        Priority.LOW:      '🟢',
    }
    priority_labels = {
        Priority.CRITICAL: 'Critical',
        Priority.HIGH:     'High Priority',
        Priority.MEDIUM:   'Medium Priority',
        Priority.LOW:      'Low Priority',
    }

    #recommendations_result from generate_all_recommendations()
    return [
        {
            'title':          rec.title,
            'description':    rec.description,
            'priority_icon':  priority_icons[rec.priority],
            'priority_label': priority_labels[rec.priority],
            'priority_value': rec.priority.value,
            'impact_score':   rec.impact_score,
            'category':       rec.category,
            'action_items':   rec.action_items,
        }
        for rec in recommendations_result.get('all_recommendations', [])
    ]

#Short message for frontend based on total and severity of the recommendations
def get_recommendation_summary(recommendations_result: Dict) -> str:
    total       = recommendations_result.get('total_count', 0)
    critical    = len(recommendations_result.get('critical_recommendations', []))
    high        = len(recommendations_result.get('high_recommendations', []))
    improvement = recommendations_result.get('estimated_improvement', 0.0)

    if total == 0:
        return 'Excellent! No major recommendations. Your resume is well-optimized.'

    if critical > 0:
        return (
            f'Found {total} recommendation(s) including {critical} critical issue(s). '
            f'Addressing these could improve your score by up to {improvement:.0f} points.'
        )
    elif high > 0:
        return (
            f'Found {total} recommendation(s) including {high} high-priority item(s). '
            f'Addressing these could improve your score by up to {improvement:.0f} points.'
        )
    else:
        return (
            f'Found {total} recommendation(s) for improvement. '
            f'Addressing these could improve your score by up to {improvement:.0f} points.'
        )