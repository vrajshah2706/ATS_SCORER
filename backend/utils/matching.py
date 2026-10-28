"""
Compares skill keywords extracted from a resume with keywords from a job
decription (jd). 
Normalises common variations such as React.js = reactjs
use exact or fuzzy matching to divide JD skills into matched & missing lists
"""
from typing import Dict, List

from rapidfuzz import fuzz

#Mapping alternative spelling/abbreviation to common or coanoniocal name
#Helps macther treat common variants as equivalent
SKILL_ALIASES: Dict[str, str] = {
    'reactjs':       'react',
    'react.js':      'react',
    'angularjs':     'angular',
    'vuejs':         'vue',
    'vue.js':        'vue',
    'nextjs':        'next.js',
    'nodejs':        'node.js',
    'node':          'node.js',
    'expressjs':     'express',
    'express.js':    'express',
    'springboot':    'spring boot',
    'golang':        'go',
    'ml':            'machine learning',
    'ai':            'artificial intelligence',
    'nlp':           'natural language processing',
    'cv':            'computer vision',
    'k8s':           'kubernetes',
    'sklearn':       'scikit-learn',
    'postgres':      'postgresql',
    'dotnet':        '.net',
    'tailwindcss':   'tailwind',
    'amazon web services': 'aws',
    'google cloud':  'gcp',
    'pyspark':       'spark',
    'huggingface':   'hugging face',
}

#looks for cleaned string in SKILL_ALIASES
def normalise_skill(skill:str) -> str:
    cleaned = skill.strip().lower() #removed whitespace and converts to lower
    return SKILL_ALIASES.get(cleaned, cleaned) #return alias or cleaned string

def fuzzy_match_keywords(
        resume_keywords: List[str],
        jd_keywords: List[str],
        threshold: int= 80
) -> Dict[str, List[str]]:
    resume_normalised = {normalise_skill(kw) : kw for kw in resume_keywords}
    jd_normalised =  {normalise_skill(kw) : kw for kw in jd_keywords}

    matched_jd_originals = []
    missing_jd_originals = []

    #Chek each JD skill 
    for jd_canon, jd_original in jd_normalised.items():
        #1. Exact canonical match 
        if jd_canon in resume_normalised:
            matched_jd_originals.append(jd_original)
            continue 

        #2. Fuzzy match against all resume canoncial names
        best_score =0
        #compare that JD skill with every normalised resume skill
        for resume_canon in resume_normalised:
            score= fuzz.token_sort_ratio(jd_canon, resume_canon)
            best_score = max(best_score, score) #keeps the highest score it finds 

        #JD skill goes into matched else missing
        if best_score >= threshold:
            matched_jd_originals.append(jd_original)
        else: 
            missing_jd_originals.append(jd_original)


    return {
        "matched" : sorted(matched_jd_originals),
        "missing" : missing_jd_originals,

    }


