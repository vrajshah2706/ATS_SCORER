"""
- defines the API endpoints for the resume analysis backend
- groups under the /api/v1 prefix.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, File, Form , Header, Request, UploadFile
from backend.models.schemas import AnalysisResponse, ComponentScores, JDComparison, SkillValidationDetails
#Default values 
from backend.utils.file_utils import (
    get_default_grammar_results,
    get_default_location_results,
    get_default_skill_validation_results,
)

logger = logging.getLogger("ats_resume_scorer")

#Use Prefix to define route e.g " /api/v1/'x' "
router = APIRouter(prefix="/api/v1", tags=["Analysis"])

#Removing any emojis
def _clean(text:str) -> str:
    for prefix in ('✅', '🌟', '❌', '⚠️', '📝', '🔴', '🟡', '🟢', '🟠', '👍'):
        text = text.lstrip(prefix)
    return text.strip()

############################# 
# Overview of All Endpoints #
############################# 

#Returns API name, version, and list of endpoints used 
@router.get("/")
async def root():
    return {
        "name": "ATS Resume Analyser API",
        "version": "1.0.0",
        "endpoints": {
            "POST   /api/v1/analyse-resume" : "Analyse a resume",
            "GET    /api/v1/history "       : "Get user history",
            "DELETE /api/v1/history/:id"    : "Delete a history entry",
            "GET    /api/v1/health"         : "Health check",
            "POST   /api/v1/generate-pdf"   : "Generate PDF report from data"
        },
    }


#Async handles other requests instead of blocking the whole server
@router.post("/analyse-resume", response_model=AnalysisResponse)
async def analyse_resume(
    request: Request,
    resume: UploadFile = File(..., description="Resume file - PDF or DOCX, max 5 MB"),
    #Reads Form fields
    job_description: str = Form('', description="Job description text (optional)"),
    user_id: str = Form("", description="Clerk user ID for saving history (optional)")
): 
    warnings: List[str] = []

    #Uses NLP and Embedding model stored in request.app.state
    nlp = request.app.state.nlp
    embedder = request.app.state.embedder 


    try:
        file_bytes = await resume.read()
        file_name= resume.filename or "resume" #if filename none, name it to resume  

        #parsing the resume file
        from backend.services.resume_parser import (
            FileParsingError,
            FileValidationError,
            parse_resume_file
        )

        resume_text, _metadata = parse_resume_file(file_bytes, file_name)
        logger.info(f"Parsed  '{file_name}': {len(resume_text)} chars extracted")

    except Exception as exc: 
        logger.error(f"File parsing failed: {exc}")
        raise HTTPException(
            status_code=422, 
            detail = f"Could not read or parse the resume: {exc}",
        )

    #Full Analysis Pipeline 
    try: 
        from ATS_SCORER.backend.services.resume_analyser import analyse_full_resume

        #calling function from resume_anlyser file
        result = analyse_full_resume(
            resume_text = resume_text,
            nlp = nlp,
            embedder=embedder,
            job_description=job_description
        )

    except Exception as exc:
        logger.error(f"Full analysis pipeline failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Analysis pipeline failed: {exc}")

    from backend.models.schemas import ComponentScores
    #Extract jd_comparison details
    jd_comparison_result = None
    if result.get("jd_comparison"):
        jd_comparison_result = JDComparison(
           match_percentage=round(float(result['jd_comparison'].get('match_percentage', 0.0)), 1),
            semantic_similarity=round(float(result['jd_comparison'].get('semantic_similarity', 0.0)), 3),
            matched_keywords=result['jd_comparison'].get('matched_keywords', [])[:20],
            missing_keywords=result['jd_comparison'].get('missing_keywords', [])[:15],
            skills_gap=result['jd_comparison'].get('skills_gap', [])[:10],
        )

    #Convert detailed feedback objects from prediction into what schema expects
    detailed_fb = result.get("detailed_feedback", [])

    #skill validation 
    svd_raw = result.get("skill_validation_details") or {}
    skill_val_details = SkillValidationDetails(
        validated       = svd_raw.get('validated', []),
        unvalidated     = svd_raw.get('unvalidated', []),
        total           = svd_raw.get('total', 0),
        validated_count = svd_raw.get('validated_count', 0),
        validation_pct  = svd_raw.get('validation_pct', 0.0),
    )

    #Convert the anlysis result into response-schema objects.
    response = AnalysisResponse(
        ATS_score=result['ats_score'],
        component_scores=ComponentScores(**result['component_scores']),
        issues_summary=result['issues_summary'],
        detailed_feedback=detailed_fb,
        jd_match_analysis=jd_comparison_result,
        skill_validation_details=skill_val_details,

        # Retro-compatibility fields
        ats_score=result['ats_score'],
        keyword_match=jd_comparison_result.match_percentage if jd_comparison_result else 0.0,
        missing_keywords=result.get('missing_keywords', []),
        matched_keywords=result.get('matched_keywords', []),
        skills=list(result.get('skills', [])[:20]),
        jd_comparison=jd_comparison_result,
        interpretation=result.get('interpretation', '')
    )

    #Saving result to user's history
    try: 
        from backend.database.supabase_db import save_analysis
        await save_analysis(user_id, file_name, result)
    except Exception as exc:
        logger.warning(f"History save failed (non-blocking): {exc}")

    #Returns result as AnalysisResponse
    return response



################################ 
# HEALTH CHECK FOR APPLICATION #
################################

#Health check - confirms models are loaded and the API is ready
@router.get("/health") 
async def health_check(request: Request):
    return {
        'status':          'healthy',
        'nlp_loaded':      request.app.state.nlp is not None,
        'embedder_loaded': request.app.state.embedder is not None,
    }

####################
# GET User History #
####################

#Retrieve all past analysis results for a user
#The user ID is sent via the X-User-ID header (set by frontend)
@router.get("/history")
async def get_history(user_id: str = Depends(get_current_user)):
    """Return the signed-in user's past analyses (identity comes from the JWT)."""
    from backend.database.supabase_db import get_user_history
    try:
        return await get_user_history(user_id)
    except Exception as exc:
        logger.error(f'History fetch failed: {exc}')
        raise HTTPException(status_code=500, detail=f'Could not load history: {exc}')

############################################## 
# DELETE Specific analysis from User History #
############################################## 

#Deletes a saved analysis, signed in user only.
@router.delete("/history/{analysis_id}")
async def delete_history_entry(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    #Delete one analysis from the signed-in user's history 
    from backend.database.supabase_db import delete_analysis
    try:
        success = await delete_analysis(analysis_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail='Analysis not found or not owned by this user.')
        return {'status': 'deleted', 'id': analysis_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f'History delete failed: {exc}')
        raise HTTPException(status_code=500, detail=f'Could not delete: {exc}')


################
# Generate PDF #
################
@router.post("/generate-pdf")
async def generate_pdf(
    data: AnalysisResponse,
    user_id: str = Depends(get_current_user),
):
    from backend.services.report_generator import generate_html_reports
    from backend.services.pdf_export import generate_combined_pdf
    from fastapi.responses import Response

    try:
        #Render/Prepare HTML report
        html_docs = generate_html_reports(data.model_dump())
        #Convert to PDF
        pdf_bytes = generate_combined_pdf(html_docs)

        #Returns as downloable PDF
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=ats_report.pdf"
            }
        )
    except Exception as e:
        logger.error(f'Failed to generate PDF: {e}')
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")

#################################
# GET User Analysis Based on ID #
#################################

#Finds a saved analysis and generates a PDF for it
@router.get('/history/{analysis_id}/pdf')
async def generate_history_pdf(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    from backend.database.supabase_db import get_user_history
    from backend.services.report_generator import generate_html_reports
    from backend.services.pdf_export import generate_combined_pdf
    from fastapi.responses import Response

    #getting user history
    history = await get_user_history(user_id)
    #Finding any analysis in history
    analysis_data = next((item["analysis_result"] for item in history if item["id"] == analysis_id), None)

    #Raise error if no analysis 
    if not analysis_data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        #Render/Prepare HTML report
        html_docs = generate_html_reports(analysis_data)
        #Convert to PDF
        pdf_bytes = generate_combined_pdf(html_docs)

        #Returns as downloable PDF
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=ats_report_{analysis_id}.pdf"
            }
        )
    except Exception as e:
        logger.error(f'Failed to generate PDF for history: {e}')
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")


