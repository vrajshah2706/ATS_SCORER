"""
Scoring and some feedback 
turns parsed resume sections, keywords, grammar, results and detected location
into component scores, an overall score and feedback. 

How the overall score works (kept simple so the numbers on screen add up):
    overall = formatting (max 20) + keywords (max 25) + content (max 25)
              + skill validation (max 15) + ATS compatibility (max 15)
              - job description keyword-gap penalty (only when a JD is supplied)
"""
import re
import spacy 
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Dict, List,Optional, Tuple 

from backend.utils.file_utils import log_warning
from backend.utils.matching import fuzzy_match_keywords, normalise_skill, SKILL_ALIASES


#########################
#  DETECTION PATTERNS   #
#########################

#Full street address, e.g. "12 Smith Street", "4/12 Smith St", "5 COLLINS STREET".
#The street name must be capitalised so ordinary phrases are not mistaken for addresses.
STREET_ADDRESS_PATTERN = (
    r'\b\d{1,5}[A-Za-z]?(?:\s*[/-]\s*\d{1,5})?\s+'
    r'(?:(?:[A-Z][a-z]+|[A-Z]{2,})\s+){1,3}'
    r'(?i:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|'
    r'Way|Place|Pl|Parade|Pde|Crescent|Cres|Terrace|Tce|Highway|Hwy)\b'
)

#Postal codes are only matched in formats that cannot be confused with phone numbers or other digits.
POSTAL_CODE_PATTERNS = [
    r'\b(?:VIC|NSW|QLD|SA|WA|TAS|ACT|NT)\s+\d{4}\b',                  # Australia: "VIC 3000"
    r'\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b',                               # US: "CA 94105"
    r'[A-Za-z]\s*[,\-–]\s*\d{6}\b',                                   # India: "Mumbai - 400001"
    r'\b(?i:pin(?:\s*code)?|post(?:al)?\s*code|zip(?:\s*code)?)\b\s*[:\-]?\s*\d{4,6}\b',  # labelled
]

#Patterns that count as a measurable achievement. Shared by the content score and the
#"No Quantifiable Achievements" feedback so the two can never disagree.
QUANTIFIED_PATTERNS = [
    r'\d+(?:\.\d+)?\s*%',                                    # 40%
    r'[$€£₹]\s?\d',                                          # $5, ₹10
    r'\d+(?:\.\d+)?[kKmMbB]\b',                              # 10K, 2M
    r'\d+\+',                                                # 500+
    r'\d{1,3}(?:,\d{3})+',                                   # 10,000
    r'\b\d+\s*(?:users|customers|clients|projects|hours|days|months|years|requests|records|'
    r'endpoints|features|members|students|people|teams|transactions|services|applications|apps|tests|pages)\b',
    r'(?:increased|decreased|improved|reduced|grew|saved|boosted|cut|raised)\s+(?:\w+\s+){0,3}(?:by\s+)?\d+',
    r'\b(?:team|group)\s+of\s+\d+',                          # team of 5
]


##################################
#  SCORING AND LOCATION HELPERS  #
##################################

# Helper function for calculating tiers
def _tier_score(n: float, tiers:list) -> float:
    for threshold, pts in tiers:
        if n >= threshold:
            return pts 

    return 0.0

#Location/Privacy detection - searches the resume text in 3 ways
#ignore_terms: skills/keywords from the resume, so tech terms spaCy mistakes for places (e.g. "Java") are not counted
def detect_location_info(text:str, nlp: spacy.Language, ignore_terms: Optional[List[str]] = None) -> Dict:
    ignore = {t.strip().lower() for t in (ignore_terms or []) if isinstance(t, str)}
    locations = []
    seen_places = set()

    #each method catches something else that might be missed by the previous one or cant detect
    #method 1: spacy named entity reconginiton - place names (each distinct place counted once)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ not in ('GPE', 'LOC'):
            continue
        key = ent.text.strip().lower()
        if not key or key in ignore or key in seen_places:
            continue
        seen_places.add(key)
        locations.append({'text': ent.text, 'type': ent.label_.lower(), 'start': ent.start_char})

    #method 2: street address regex
    for match in re.finditer(STREET_ADDRESS_PATTERN, text):
        locations.append({'text': match.group().strip(), 'type': 'address', 'start': match.start()})

    #method 3: postal / ZIP / PIN code regexes (several countries, formats that avoid phone numbers)
    for pattern in POSTAL_CODE_PATTERNS:
        for match in re.finditer(pattern, text):
            locations.append({'text': match.group().strip(), 'type': 'postal_code', 'start': match.start()})

    place_count = sum(1 for loc in locations if loc['type'] in ('gpe', 'loc'))
    has_address = any(loc['type'] == 'address'     for loc in locations)
    has_postal  = any(loc['type'] == 'postal_code' for loc in locations)

    #Risk rules:
    #  street address and/or postal code -> high (a real privacy risk, penalised)
    #  many different place names        -> medium (location sprinkled through the resume, small penalty)
    #  a few place names (e.g. "City, State" in the header) -> low, no penalty - that is normal and recommended
    if has_address and has_postal:
        privacy_risk, penalty = "high" , 5.0
    elif has_address or has_postal:
        privacy_risk, penalty = "high" , 4.0
    elif place_count > 4:
        privacy_risk, penalty = "medium" , 2.0
    elif place_count > 0:
        privacy_risk, penalty = "low" , 0.0
    else: 
        privacy_risk, penalty = "none" , 0.0

    recommendations = []
    if privacy_risk == "none":
        recommendations.append("No privacy concerns detected.")
    if has_address:
        recommendations.append("Remove full street addresses — ATS systems don't need this and it's a privacy risk.")
    if has_postal:
        recommendations.append("Remove postal / ZIP / PIN codes — this level of location detail is unnecessary.")
    if privacy_risk == "medium":
        recommendations.append("Consider reducing location mentions. 'City, State' in the contact header is sufficient.")
    if privacy_risk == "low":
        recommendations.append("Location detail looks appropriate ('City, State' style).")

    #returns detected locations, privacy risk, recommendations and penalty
    return {
        'location_found':     len(locations) > 0,
        'detected_locations': locations,
        'privacy_risk':       privacy_risk,
        'recommendations':    recommendations,
        'penalty_applied':    penalty,
    }


#################################
#  SKILL VALIDATION HELPERS     #
#################################

#All spellings of a skill worth searching for: the skill itself, its canonical alias and known aliases,
#plus hyphen / space / dot variants (e.g. "scikit-learn", "scikit learn", "sklearn", "Node.js", "nodejs")
def _skill_variants(skill: str) -> List[str]:
    base = skill.strip().lower()
    canon = normalise_skill(base)
    forms = {base, canon}
    forms.update(alias for alias, target in SKILL_ALIASES.items() if target == canon)

    expanded = set()
    for form in forms:
        expanded.update({
            form,
            form.replace('-', ' '),
            form.replace(' ', '-'),
            form.replace('.', ''),
            form.replace(' ', ''),
        })
    return [v for v in expanded if v]

#True if the skill appears in the text as a whole word/term (not inside another word).
#Very short skills (C, R, Go) must match case-sensitively so they don't match ordinary words or letters.
def _contains_skill(skill: str, text: str) -> bool:
    skill = skill.strip()
    if not skill or not text:
        return False

    if len(skill) <= 2:
        pattern = rf'(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9+#])'
        return re.search(pattern, text) is not None

    lowered = text.lower()
    for variant in _skill_variants(skill):
        if re.search(rf'(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])', lowered):
            return True
    return False

#Splits text into sentence / bullet sized pieces. A short skill compared with a whole paragraph
#scores low even when the paragraph clearly uses it, so the semantic fallback compares against pieces.
def _split_into_chunks(text: str) -> List[str]:
    parts = re.split(r'[\n\r•·▪◦]+|(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) > 10]

def _unit_vectors(vectors) -> np.ndarray:
    arr = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)

#Semantic fallback: for skills with no exact evidence, check whether any sentence in a project/experience
#means the same thing. All skills and all sentences are embedded in two batched calls (fast).
def _add_semantic_evidence(
        pending: List[str],
        sources: List[Tuple[str, str]],
        evidence: Dict[str, List[str]],
        similarity: Dict[str, float],
        embedder: SentenceTransformer,
        threshold: float,
) -> None:
    chunk_texts: List[str] = []
    chunk_source: List[int] = []
    for idx, (_, text) in enumerate(sources):
        for chunk in _split_into_chunks(text):
            chunk_texts.append(chunk)
            chunk_source.append(idx)

    if not chunk_texts:
        return

    try:
        skill_vecs = _unit_vectors(embedder.encode(pending))
        chunk_vecs = _unit_vectors(embedder.encode(chunk_texts))
    except Exception as e:
        #if embeddings fail log warning - skills simply stay unvalidated
        log_warning(f"Semantic skill matching failed: {e}", context="ats_scorer")
        return

    sims = skill_vecs @ chunk_vecs.T   #cosine similarity: rows = skills, columns = sentences
    source_of_chunk = np.array(chunk_source)

    for i, skill in enumerate(pending):
        for idx, (label, _) in enumerate(sources):
            mask = source_of_chunk == idx
            if not mask.any():
                continue
            best = float(sims[i, mask].max())
            similarity[skill] = max(similarity[skill], best)
            if best >= threshold and label not in evidence[skill]:
                evidence[skill].append(label)


#Skill validation - checks whether each listed skill has evidence in the resume's project or experience 
#Evidence is looked for in: project title + description + technologies, and experience title/company/description
def validate_skills_with_projects(
        skills: List[str],
        projects: List[Dict],
        experience_entries: List[Dict],
        embedder: SentenceTransformer,
        threshold: float=0.6
) -> Dict:
    #remove duplicate skills (case-insensitive) so the same skill is never counted twice
    unique_skills: List[str] = []
    seen = set()
    for skill in skills or []:
        if not isinstance(skill, str) or not skill.strip():
            continue
        key = skill.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_skills.append(skill.strip())
    skills = unique_skills

    #default  values in no skills 
    if not skills:
        return {
            'validated_skills':      [],
            'unvalidated_skills':    [],
            'validation_percentage': 0.0,
            'skill_project_mapping': {},
            'validation_score':      0.0,
        }

    #Evidence sources: each project (title + description + technologies) and one combined experience text
    sources: List[Tuple[str, str]] = []
    for project in projects or []:
        if isinstance(project, dict):
            technologies = project.get('technologies') or []
            if isinstance(technologies, str):
                technologies = [technologies]
            text = ' '.join([
                project.get('title') or '',
                project.get('description') or '',
                ', '.join(str(t) for t in technologies),
            ]).strip()
            label = project.get('title') or 'Untitled Project'
        else:
            text, label = str(project), 'Untitled Project'
        if text:
            sources.append((label, text))

    experience_text = ' '.join(
        f"{e.get('job_title') or ''} {e.get('company') or ''} {e.get('description') or ''}"
        for e in (experience_entries or [])
        if isinstance(e, dict)
    ).strip()
    if experience_text:
        sources.append(("Experience Section", experience_text))

    evidence: Dict[str, List[str]] = {skill: [] for skill in skills}
    similarity: Dict[str, float] = {skill: 0.0 for skill in skills}

    #Step 1 - exact (whole word) match in every source
    for skill in skills:
        for label, text in sources:
            if _contains_skill(skill, text):
                if label not in evidence[skill]:
                    evidence[skill].append(label)
                similarity[skill] = 1.0

    #Step 2 - semantic match, only for skills that still have no evidence
    pending = [skill for skill in skills if not evidence[skill]]
    if pending and sources:
        _add_semantic_evidence(pending, sources, evidence, similarity, embedder, threshold)

    validated_skills = []
    unvalidated_skills = []
    skill_project_mapping = {}

    for skill in skills:
        skill_project_mapping[skill] = evidence[skill]
        if evidence[skill]:
            validated_skills.append({'skill': skill, 'projects': evidence[skill], 'similarity': similarity[skill]})
        else:
            unvalidated_skills.append(skill)

    validation_percentage = len(validated_skills) / len(skills)
    validation_score       = validation_percentage * 15.0

    return {
        'validated_skills':      validated_skills,
        'unvalidated_skills':    unvalidated_skills,
        'validation_percentage': validation_percentage,
        'skill_project_mapping': skill_project_mapping,
        'validation_score':      validation_score,
    }

########################
#   COMPONENT SCORES   #
########################

#Format calculator - score 
# awards points for populared sections, >=3 , a summary, projects & bullet points, cap result at 20  
def _calc_formatting_score(parsed_resume: Dict, text:str) -> float:
    score = 0.0

    exp_entries = [e for e in parsed_resume.get("experience", []) if isinstance(e, dict)]
    edu_entries =  [e for e in parsed_resume.get("education", []) if isinstance(e, dict)]
    skills = parsed_resume.get("skills", [])
    summary = parsed_resume.get("professional_summary") or ""
    proj_entries = [p for p in parsed_resume.get("projects" , []) if isinstance(p, dict)]

    if exp_entries and any(e.get('job_title') or e.get('description') for e in exp_entries):
        score += 3.0
    if edu_entries:
        score += 2.0
    if len(skills) >= 3:
        score += 2.0
    if len(summary) > 30:
        score += 1.5
    if proj_entries:
        score += 1.5

    
    bullet_count = sum(
        1 for line in text.split('\n')
        if re.match(r'^\s*[•\-\*\◦]', line) or re.match(r'^\s*\d+\.', line)
    )
    score += _tier_score(bullet_count, [(15,5.0),(10,4.0),(5,3.0),(3,2.0),(1,1.0)])

    filled = sum(1 for has_it in [
            bool(exp_entries), bool(edu_entries), bool(skills),
            bool(summary.strip()), bool(proj_entries),
        ] if has_it)
    score += _tier_score(filled, [(4,5.0),(3,4.0),(2,3.0),(1,2.0)])

    return min(20.0, max(0.0, score))

#Keyword calculator - score
#awards additional points for matching resume terms against JD keywors, cap at 25
def _calc_keywords_score(resume_keywords: List[str] , skills: List[str], jd_keywords: Optional[List[str]]=None) -> float:
    score=0.0

    score += _tier_score(len(resume_keywords), [(20,10.0),(15,8.0),(10,6.0),(5,4.0),(3,2.0)])
    score += _tier_score(len(skills),          [(15,10.0),(10,8.0),(7,6.0),(5,4.0),(3,2.0)])

    if jd_keywords:
        all_resume_terms = list(set(resume_keywords + skills))
        fuzzy_result     = fuzzy_match_keywords(all_resume_terms, jd_keywords, threshold=80)
        match_pct        = len(fuzzy_result['matched']) / len(jd_keywords) if jd_keywords else 0
        score += _tier_score(match_pct, [(0.7,5.0),(0.5,4.0),(0.3,3.0),(0.2,2.0),(0.1,1.0)])

    elif len(resume_keywords) >= 10: 
        score += 3.0

    return min(25.0, max(0.0, score))

#Content quality score (max 25) - action verbs (10 pts), quantified achievements (5 pts), grammar (10 pts)
#Grammar checking is not implemented yet. When it is unavailable it is left out and the other 15 points
#are scaled up to the full 25, instead of handing every resume 10 free grammar points.
def _calc_content_score(
        text:str,
        action_verbs: list[str],
        grammar_results: Dict
) -> float:
    verbs_pts = _tier_score(len(action_verbs), [(15,10.0),(10,8.0),(7,6.0),(5,4.0),(3,2.0)])

    achievement_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in QUANTIFIED_PATTERNS)
    achievements_pts = _tier_score(achievement_count, [(10,5.0),(7,4.0),(5,3.0),(3,2.0),(1,1.0)])

    if grammar_results.get('_component_status') == 'unavailable':
        score = (verbs_pts + achievements_pts) / 15.0 * 25.0
    else:
        grammar_penalty = grammar_results.get('penalty_applied', 0.0)
        score = verbs_pts + achievements_pts + max(0.0, 10.0 - grammar_penalty / 2.0)

    return min(25.0, max(0.0, score))

# Skill validation score
# uses the validation score from earlier skill evidence chekck, cap at 15
def _calc_skill_validation_score(validation_results: Dict) -> float:
    return min(15.0, max(0.0, validation_results.get("validation_score", 0.0)))

#ATS compatibiltiy score
#starts at 15, deducts for location privacy, concerns, unusual character, short sections and may add points
def _calc_ats_compatibility_score(text: str, location_results: Dict, parsed_resume:Dict) -> float:
    score=15.0

    #deduction 1 - location privacy (street address / postal code / too many place names)
    score -= location_results.get("penalty_applied", 0.0)

    #deduction 2 - concerns/unusual characters
    special_chars = len(re.findall(r'[│┤├┼┴┬╔╗╚╝═║╠╣╦╩╬]', text))
    if special_chars > 20:    score -= 2.0
    elif special_chars > 10:  score -= 1.0

    exp_entries  = [e for e in parsed_resume.get('experience', []) if isinstance(e, dict)]
    edu_entries  = [e for e in parsed_resume.get('education', [])  if isinstance(e, dict)]
    skills_count = len(parsed_resume.get('skills', []))

    exp_desc_len = sum(len(e.get('description') or '') for e in exp_entries)
    edu_desc_len = sum(len((e.get('degree') or '') + (e.get('institution') or '')) for e in edu_entries)  # Handle None to prevent string concatenation errors

    #deduction 3 - short sections 
    short_sections = sum([
        bool(exp_entries) and exp_desc_len < 20,
        bool(edu_entries) and edu_desc_len < 20,
        bool(parsed_resume.get('skills')) and skills_count < 2,
    ])
    if short_sections >= 2:    score -= 2.0
    elif short_sections >= 1:  score -= 1.0

    # add points
    if exp_entries and skills_count > 5:
        score += 1.0

    return min(15.0, max(0.0, score))


####################
#   Orchestartor   #
####################
#Score aggregation and final interpretation 
#overall = sum of the five component scores (max 100) minus the job description keyword-gap penalty
def calculate_overall_score(
    text: str,
    parsed_resume: Dict,
    skills: List[str],
    keywords: List[str],
    action_verbs: List[str],
    skill_validation_results: Dict,
    grammar_results: Dict,
    location_results: Dict,
    jd_keywords: Optional[List[str]] = None,
    experience_months: int = 0,
) -> Dict:

    #calls each function - every score is already capped at its own maximum
    formatting_score        = _calc_formatting_score(parsed_resume, text)          # out of 20
    keywords_score          = _calc_keywords_score(keywords, skills, jd_keywords)  # out of 25
    content_score           = _calc_content_score(text, action_verbs, grammar_results)  # out of 25
    skill_validation_score  = _calc_skill_validation_score(skill_validation_results)    # out of 15
    ats_compatibility_score = _calc_ats_compatibility_score(text, location_results, parsed_resume)  # out of 15

    #The maximums add up to exactly 100, so the overall score is simply their sum.
    score = (
        formatting_score
        + keywords_score
        + content_score
        + skill_validation_score
        + ats_compatibility_score
    )

    #Location privacy is already deducted inside the ATS compatibility score, and grammar is handled
    #inside the content score, so the only extra adjustment is the job description keyword gap.
    penalties = {}
    bonuses   = {}

    if jd_keywords and len(jd_keywords) > 0:
        #combine resume keywords and skills
        all_resume_terms = list(set((keywords or []) + (skills or [])))
        #fuzzy matching with threshold 80
        fuzzy_result     = fuzzy_match_keywords(all_resume_terms, jd_keywords, threshold=80)
        #compute pct
        missing_pct      = len(fuzzy_result['missing']) / len(jd_keywords)

        #deduct based on missing %
        if missing_pct > 0.7:
            penalties['missing_jd_keywords'] = 15.0
        elif missing_pct > 0.5:
            penalties['missing_jd_keywords'] = 10.0
        elif missing_pct > 0.3:
            penalties['missing_jd_keywords'] = 5.0

    score -= sum(penalties.values())

    #final score within 0-100
    overall_score = min(100.0, max(0.0, score))
    interpretation = _generate_score_interpretation(overall_score)

    return {
        'overall_score':           round(overall_score, 1),
        'formatting_score':        round(formatting_score, 1),
        'keywords_score':          round(keywords_score, 1),
        'content_score':           round(content_score, 1),
        'skill_validation_score':  round(skill_validation_score, 1),
        'ats_compatibility_score': round(ats_compatibility_score, 1),
        'overall_interpretation':  interpretation,
        'penalties':               penalties,
        'bonuses':                 bonuses,}

#Interpretation of overall score - maps overall score to a description
def _generate_score_interpretation(overall_score: float) -> str:
    if overall_score >= 90:    return 'Excellent! Your resume is highly optimized for ATS systems.'
    elif overall_score >= 80:  return 'Great! Your resume should perform well with most ATS systems.'
    elif overall_score >= 70:  return 'Good! Your resume is ATS-friendly with room for minor improvements.'
    elif overall_score >= 60:  return 'Fair. Your resume needs some improvements to be fully ATS-compatible.'
    elif overall_score >= 50:  return 'Below Average. Significant improvements needed for ATS compatibility.'
    else:                      return 'Poor. Your resume requires major revisions to pass ATS screening.'
