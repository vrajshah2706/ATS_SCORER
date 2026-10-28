"""
Compares resume with with a JD
1. Semantic similarty compares the overall text
2. keyword matching checks with job description keywords appear in resume's keywords
3. skills gap analysis looks for possible skills in the JD that are not in resume
4. Match % combines semantic similarity and keywords overlap into one score. 
"""
from typing import List, Dict
import numpy as np
import spacy
from sentence_transformers import SentenceTransformer

from backend.utils.matching import fuzzy_match_keywords, normalise_skill
from rapidfuzz import fuzz

#measures how similar the resume and JD are in meaning
def calculate_semantic_similarity(
        resume_text: str, jd_text: str, embedder: SentenceTransformer
) -> float:
    resume_emb = embedder.encode(resume_text[:5000], convert_to_tensor=False)
    jd_emb = embedder.encode(jd_text[:5000], convert_to_tensor=False)

    #calculating cosine similarity between those two vectoors using numpy
    similarity = np.dot(resume_emb, jd_emb) / (
        np.linalg.norm(resume_emb) * np.linalg.norm(jd_emb)
    )

    #clips to range 0.0-1.0
    return float(np.clip(similarity, 0.0, 1.0))


def identify_matched_keywords (
        resume_keywords: List[str], jd_keywords: List[str] 
) -> List[str] :
    #calling function from matching.py file
    result = fuzzy_match_keywords(resume_keywords, jd_keywords, threshold=80)

    #returns "matched" list from result
    return result["matched"]

def identify_missing_keywords(
        resume_keywords:List[str], jd_keywords: List[str], top_n: int = 15
) -> List[str]:
    #calling function from matching.py file
    result = fuzzy_match_keywords(resume_keywords, jd_keywords, threshold=80)

    #returns "missing" list from result, limit to first top_n
    return result["missing"][:top_n]

#finds skills mentioned in the JD that are absent from the resume's skills
def analyse_skills_gap (
        resume_skills: List[str] , jd_text: str, nlp: spacy.Language
) -> List[str]:
    #spaCy process up to first 5000 characters of JD
    doc = nlp(jd_text[:5000])
    jd_skills = set()

    #collect certain named entities and noun phrases as candidate skills
    for ent in doc.ents:
        if ent.label_ in ["PRODUCT", "ORG", "LANGUAGE"]:
            jd_skills.add(ent.text.lower())

    for chunk in doc.noun_chunks:
        ct = chunk.text.lower().strip()
        if 1 <= len(ct.split()) <= 4: 
            jd_skills.add(ct)

    #Normalise resume skills for comparison (calling function from matching.py)
    resume_normalised = {normalise_skill(s) for s in resume_skills}

    gap = []
    for jd_skill in jd_skills:
        jd_norm = normalise_skill(jd_skill)

        #Check canonical match first
        if jd_norm in resume_normalised:
            continue

        #Then try fuzzy match against all resume skills
        best_score = max(
            (fuzz.token_sort_ratio(jd_norm, rs) for rs in resume_normalised),
            default=0
        )
        #<75 are considered gaps
        if best_score < 75:
            gap.append(jd_skill)

    #sorts alphabetically and returns at most 20
    return sorted(gap)[:20]


def calculate_match_percentage(
        resume_keywords:List[str],
        jd_keywords: List[str],
        semantic_simlarity: float,
) -> float:
    #if no JD keywords, 0 match 
    if not jd_keywords:
        return 0.0
    
    matched = identify_matched_keywords(resume_keywords, jd_keywords)
    keyword_overlap = len(matched) / len(jd_keywords)
    #keyword overlap contirbute 60% and semantic similarity contirbutes 40%
    match_pct = (keyword_overlap * 0.6 + semantic_simlarity * 0.4) * 100

    return float(np.clip(match_pct, 0.0, 100.0))

#####################
#   MAIN FUNCTION   #
#####################
def compare_resume_with_jd(
    resume_text: str,
    resume_keywords: List[str],
    resume_skills: List[str],
    jd_text: str,
    jd_keywords: List[str],
    embedder: SentenceTransformer,
    nlp: spacy.Language,
) -> Dict:
    #calls functions 
    semantic_similarity = calculate_semantic_similarity(resume_text, jd_text, embedder)
    matched_keywords    = identify_matched_keywords(resume_keywords, jd_keywords)
    missing_keywords    = identify_missing_keywords(resume_keywords, jd_keywords)
    skills_gap          = analyse_skills_gap(resume_skills, jd_text, nlp)
    match_percentage    = calculate_match_percentage(
        resume_keywords, jd_keywords, semantic_similarity
    )

    return {
        'match_percentage':    match_percentage,
        'semantic_similarity': semantic_similarity,
        'matched_keywords':    matched_keywords,
        'missing_keywords':    missing_keywords,
        'skills_gap':          skills_gap,
    }
