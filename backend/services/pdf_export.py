"""
- Converts rendered HTML (from report_generator) into one downloadable PDF
"""
import io
import logging

#import weasyprint's html and css classes
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_INSTALLED = True
except ImportError:
    WEASYPRINT_INSTALLED = False

logger = logging.getLogger("ats_resume_scorer")
#Parameter- Dictionary of report [name, HTML string] from report_generator 
def generate_combined_pdf(html_docs: dict[str, str]) -> bytes:
    #Check if WeasyPrint is available, if not raise error
    if not WEASYPRINT_INSTALLED:
        raise ImportError("WeasyPrint is not installed. PDF generation unavailable.")
        
    documents = []
    
    # Render all 3 HTML strings to WeasyPrint Document objects (documents)
    for name, html_str in html_docs.items():
        doc = HTML(string=html_str).render()
        documents.append(doc)
    
    # Merge them into the first document
    first_doc = documents[0]
    for other_doc in documents[1:]:
        for page in other_doc.pages:
            first_doc.pages.append(page)
            
    # Write combined as PDF bytes
    pdf_bytes = first_doc.write_pdf()
    
    return pdf_bytes