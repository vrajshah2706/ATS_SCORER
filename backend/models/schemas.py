#Declaring datatypes - to send and receive data from the API endpoints
from typing import Any, Dict, List, Optional 
from pydantic import BaseModel 

#component scores schema 
class ComponentScores(BaseModel):
    formatting: float
    keywords: float
    content: float
    skill_validation: float
    ats_compatibility: float

#job description comparison result schema
class JDComparison(BaseModel):
    match_percentage: float 
    semantic_similarity: float
    matched_keywords: List[str]
    missing_keywords: List[str]
    skills_gap: list[str]

#skill validation result schema
class SkillValidationDetails(BaseModel):
    validated: List[Dict[str, Any]] = []   #[ {"skill": "str", "projects": [str]}, ...]
    unvalidated: List[str] = []           # [ "Flask", "A/B Testing", ...]
    total: int = 0
    validated_count: int = 0 
    validated_pct : float = 0.0

#issue detail schema - to provide detailed information about issues found in the resume
class IssueDetail(BaseModel):
    issue_title: str
    severity_level: str #helps with prioritisation of issues
    ats_impact: str 
    explanation: str
    where_it_appears: str
    how_to_fix: str
    action_items: List[str] = []
    example_improvement: str

#final response schema - to send the final analysis result back to the user
class AnalysisResponse(BaseModel):
    ATS_score: float
    componnent_scores: ComponentScores
    issues_summary: List[str]
    detailed_feedback: List[IssueDetail]
    jd_match_analysis: Optional[JDComparison] = None #Uploading Job description is optional
    skill_validation_details: Optional[SkillValidationDetails] = None #Needs Job description therefore is optional