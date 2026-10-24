"""
Sends resume text or job description text to Groq's LLM
Extracts structured information
Parse the model's JSON response and fill missing fields with defaults
"""
import os
import json
import logging
from typing import Dict

from groq import Groq

logger=logging.getLogger("ats_resume_scorer")

GROQ_MODEL = "llama-3.3b-70b-versatile"

_client=None
#Using singleton pattern - avoids calling API each time (financial loss) a single call through client is made
#create groq client and reuses 
def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError("GROQ_API_KEY environment vaiable is not set")
        _client=Groq(api_key=api_key)
    return _client

######################
# FOR RESUME PARSING #
######################

#Model's role
RESUME_SYSTEM_PROMPT = (
    "You are a resume parser. Extract information from the resume."
    "and return ONLY a valid JSON object. No explanation, no markdown."
)

#Extraction instructions
RESUME_USER_PROMPT = """
Extract the following from this resume and return as JSON:
{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "linkedin": "LinkedIn URL if present, otherwise null",
  "github": "GitHub URL if present, otherwise null",
  "professional_summary": "the full text of the Summary, Profile, About Me, Objective, or Professional Summary section at the top of the resume. Copy the ENTIRE paragraph exactly as written. If no such section exists, return an empty string.",
  "skills": ["list", "of", "skills"],
  "experience": [
    {{
      "job_title": "",
      "company": "",
      "start_date": "",
      "end_date": "",
      "duration_months": 0,
      "description": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "year": ""
    }}
  ],
  "certifications": ["list of certifications"],
  "projects": [
    {{
      "title": "project name",
      "description": "what the project does and how it was built",
      "technologies": ["tech", "used"]
    }}
  ],
  "action_verbs": ["strong action verbs used in bullet points, e.g. developed, implemented, designed"],
  "keywords": ["important keywords and phrases from the resume for ATS matching"]
}}

Important instructions:
- For duration_months, calculate the number of months between start_date and end_date. If end_date is "Present" or "Current", calculate from start_date to now.
- For skills, extract ALL technical and soft skills mentioned anywhere in the resume.
- For action_verbs, find verbs that start bullet points or describe achievements.
- For keywords, extract noun phrases and technical terms relevant to ATS matching.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Resume Text:
{raw_text}
"""

#Calling groq api and sending a request  
def _call_groq(client: Groq, system_prompt:str, user_prompt:str) -> str:

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content" : system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature = 0.0,
        max_tokens = 4096 #general resume around 1-2k tokens thus gave buffer

    )

    return response.choices[0].message.content.strip() #surrounding whitespace removed


#Safety check - removing markdown or explanation from groq response 
def _try_parse_json(text:str) -> dict | None:
    #Strip markdown code fences if present 
    cleaned = text.strip()
    if cleaned.endswith("```"):
        #Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        #Remove closing fence 
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned) 
    except json.JSONDecodeError:
        return None #if parsing fails return none

#to make sure the parse json has all the valid json fields
def _validate_resume_result(result: dict) -> dict:

    defaults = {
        "name": "",
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "professional_summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "action_verbs": [],
        "keywords": [],
    }
    #Checking defaults against the result dict
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
            
        # Ensure list fields are actually lists
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    #Validate experience entries
    for exp in result.get("experience", []):
        if not isinstance(exp, dict):
            continue
        exp.setdefault("job_title", "")
        exp.setdefault("company", "")
        exp.setdefault("start_date", "")
        exp.setdefault("end_date", "")
        exp.setdefault("duration_months", 0)
        exp.setdefault("description", "")
        #Ensure duration_months is an int
        try:
            exp["duration_months"] = int(exp["duration_months"])
        except (ValueError, TypeError):
            exp["duration_months"] = 0

    #Validate project entries
    for proj in result.get("projects", []):
        if not isinstance(proj, dict):
            continue
        proj.setdefault("title", "")
        proj.setdefault("description", "")
        proj.setdefault("technologies", [])

    return result

#######################################
#   MAIN FUNCTION FOR RESUME PARSING  #
#######################################

#resume worrkflow - Extracts information from a resume
def parse_resume(raw_text: str) -> Dict:
    client= _get_client() #creates groq client 
    prompt = RESUME_USER_PROMPT.format(raw_text=raw_text)
    raw_reponse=_call_groq(client, RESUME_SYSTEM_PROMPT, prompt)
    result = _try_parse_json(raw_reponse) #Return clean JSON

    if result is not None:
        return _validate_resume_result(result)

    #if doesn't parse, log warning and make one more request with stricter instruction
    logger.warning("Groq resume parse: first attempt returned invalid JSON, retrying...")
    strict_prompt = (
        "Your previous response was not valid JSON."
        "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n" 
        + prompt
    )
    raw_reponse = _call_groq(client, RESUME_SYSTEM_PROMPT, strict_prompt)
    result = _try_parse_json(raw_reponse)
    
    if result is not None:
        return _validate_resume_result(result)

    #if retry produces unparseable JSON, raise error 
    raise ValueError(
        f"Groq returned unparseable response after retry. Raw response:\n{raw_reponse[:500]}"
    )

#########################
#  FOR JOB DESCRIPTION  #
#########################   

#Model's role
JD_SYSTEM_PROMPT = """
    "You are a job description parser. Extract information and"
    "return ONLY a valid JSON object. No explanation, no markdown"
"""

#Extraction instructions
JD_USER_PROMPT = """
Extract the following from this job description and return as JSON:
{{
  "job_title": "",
  "required_skills": ["list of must-have skills"],
  "preferred_skills": ["list of nice-to-have skills"],
  "experience_required": "",
  "education_required": "",
  "key_responsibilities": ["list of responsibilities"],
  "keywords": ["important keywords and phrases for ATS matching"]
}}

Important instructions:
- required_skills: skills explicitly stated as required or must-have.
- preferred_skills: skills stated as preferred, nice-to-have, or bonus.
- keywords: extract ALL important terms an ATS system would match against,
  including skills, technologies, certifications, and domain terms.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Job Description Text:
{raw_text}
"""

#it will ensure JD parse result has all expected keys with correct types
def _validate_jd_result(result:dict) -> dict:
   
    defaults = {
        "job_title": "",
        "required_skills": [],
        "preferred_skills": [],
        "experience_required": "",
        "education_required": "",
        "key_responsibilities": [],
        "keywords": [],
    }
    
    #Checking defaults against the result dict
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        #replace malformed list fields with empty fields
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    return result

########################################
#   MAIN FUNCTION FOR JOB DESCRIPTION  #
########################################

#Job description workflow - Extracts information from a job description
def parse_job_description(raw_text: str) -> Dict:
    client= _get_client() #creates groq client
    prompt = JD_USER_PROMPT.format(raw_text=raw_text)

    raw_reponse=_call_groq(client, JD_SYSTEM_PROMPT, prompt)
    result = _try_parse_json(raw_reponse) #Return clean JSON

    if result is not None:
        return _validate_jd_result(result)

    #if doesn't parse, log warning and make one more request with stricter instruction
    logger.warning("Groq JD parse: first attempt returned invalid JSON, retrying...")
    strict_prompt = (
        "Your previous response was not valid JSON."
        "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n" 
        + prompt
    )

    raw_reponse = _call_groq(client, JD_SYSTEM_PROMPT, strict_prompt)
    result = _try_parse_json(raw_reponse)

    if result is not None:
        return _validate_jd_result(result)
    
    #if retry produces unparseable JSON, raise error 
    raise ValueError(
        f"Groq returned unparseable response after retry. Raw response:\n{raw_reponse[:500]}"
    )
