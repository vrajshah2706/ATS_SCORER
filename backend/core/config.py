#Acting as a settings panel for the whole application 
import os
from pathlib import Path

# Load environment varaibles from .env file if it exists upon startup 
try: 
    from dotenv import load_dotenv
    load_dotenv()
except ImportError: 
    pass

# Api metadata
API_TITLE = 'ATS RESIME ANALYZER API'
APP_VERSION = '1.0.0'
APP_DESCRIPTION = 'anlayse resumes against job descriptions using nlp + ml'

ALLOWED_ORIGINS = [
    "http://localhost:5173", #Vite dev server (REACT)
    "http://localhost:3000", #Create React App fallback 
    "http://127.0.0.1:5173", 
]

#file size declaration 
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

#Supported MIME types (file types) and their short names 
SUPPPORTED_MIME_TYPES = {
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
}

SUPPORTED_FILE_EXTENSION = {'.pdf', '.doc', '.docx'}

#Model declaration  
SPACY_MODEL_PRIMARY = "en_core_web_md" #better accuracy 
SPACY_MODEL_SECONDARY = "en_core_web_sm" #faster but less accurate and fallback model 
SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", "all_mini_l6_v2") 

#Score component weights - this is a business logic treated as config so that it can be easily changed in the future
SCORE_WEIGHTS = {
    "formatting" : 20 , "keywords": 25, "content":25, 
    "skill_validation": 15, "ats_compatibility": 15
}

JD_KEYWORDS_WEIGHT = 0.6 # Weight for job description keywords match
JD_SEMENATIC_WEIGHT = 0.4 # Weight for job description semantic similarity


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")