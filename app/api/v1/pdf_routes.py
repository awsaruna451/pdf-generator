"""
PDF generation API routes
"""
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer

from app.models.pdf_models import (
    PDFGenerationRequest,
    PDFGenerationFromFileRequest,
    PDFGenerationResponse,
    ErrorResponse,
    HealthCheckResponse
)
from app.services.pdf_service import PDFService

# Initialize router
router = APIRouter(prefix="/pdf", tags=["PDF Generation"])
security = HTTPBearer(auto_error=False)

# Initialize PDF service
pdf_service = PDFService()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="Check if the PDF generation service is healthy"
)
async def health_check():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy",
        message="PDF generation service is running",
        version="1.0.0"
    )


@router.post(
    "/generate",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate PDF from HTML String",
    description="Convert HTML content string to PDF file"
)
async def generate_pdf_from_html(
    request: PDFGenerationRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate PDF from HTML content string
    
    Args:
        request: PDF generation request containing HTML content
        token: Optional authentication token
        
    Returns:
        PDFGenerationResponse: Response with PDF generation details
    """
    try:
        # Generate PDF
        pdf_path = pdf_service.html_to_pdf_reportlab(
            html_content=request.html_content,
            output_filename=request.filename,
            from_string=True
        )
        
        # Extract filename from path
        filename = os.path.basename(pdf_path)
        
        # Create download URL
        download_url = f"/pdf/download/{filename}"
        
        return PDFGenerationResponse(
            success=True,
            message="PDF generated successfully",
            filename=filename,
            file_path=pdf_path,
            download_url=download_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )


@router.post(
    "/generate-from-file",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate PDF from HTML File",
    description="Convert HTML file to PDF file"
)
async def generate_pdf_from_file(
    request: PDFGenerationFromFileRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate PDF from HTML file
    
    Args:
        request: PDF generation request containing HTML file path
        token: Optional authentication token
        
    Returns:
        PDFGenerationResponse: Response with PDF generation details
    """
    try:
        # Check if HTML file exists
        if not os.path.exists(request.html_file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"HTML file not found: {request.html_file_path}"
            )
        
        # Generate PDF
        pdf_path = pdf_service.html_to_pdf_reportlab(
            html_content=request.html_file_path,
            output_filename=request.filename,
            from_string=False
        )
        
        # Extract filename from path
        filename = os.path.basename(pdf_path)
        
        # Create download URL
        download_url = f"/pdf/download/{filename}"
        
        return PDFGenerationResponse(
            success=True,
            message="PDF generated successfully from file",
            filename=filename,
            file_path=pdf_path,
            download_url=download_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF from file: {str(e)}"
        )


@router.get(
    "/download/{filename}",
    summary="Download Generated PDF",
    description="Download a previously generated PDF file"
)
async def download_pdf(
    filename: str,
    token: Optional[str] = Depends(security)
):
    """
    Download a generated PDF file
    
    Args:
        filename: Name of the PDF file to download
        token: Optional authentication token
        
    Returns:
        FileResponse: The PDF file for download
    """
    try:
        # Validate filename
        if not filename.endswith('.pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file format. Only PDF files are allowed."
            )
        
        # Check if file exists
        if not pdf_service.file_exists(filename):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PDF file not found: {filename}"
            )
        
        # Get full file path
        file_path = pdf_service.get_pdf_file_path(filename)
        
        # Return file for download
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/pdf',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download PDF: {str(e)}"
        )


@router.get(
    "/list",
    summary="List Generated PDFs",
    description="List all generated PDF files"
)
async def list_pdfs(
    token: Optional[str] = Depends(security)
):
    """
    List all generated PDF files
    
    Args:
        token: Optional authentication token
        
    Returns:
        dict: List of generated PDF files
    """
    try:
        output_dir = pdf_service.output_dir
        
        if not os.path.exists(output_dir):
            return {"files": [], "count": 0}
        
        # Get all PDF files
        pdf_files = [
            f for f in os.listdir(output_dir) 
            if f.endswith('.pdf')
        ]
        
        # Get file details
        files_info = []
        for filename in pdf_files:
            file_path = os.path.join(output_dir, filename)
            file_stat = os.stat(file_path)
            files_info.append({
                "filename": filename,
                "size_bytes": file_stat.st_size,
                "created_at": file_stat.st_ctime,
                "download_url": f"/pdf/download/{filename}"
            })
        
        return {
            "files": files_info,
            "count": len(files_info)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list PDFs: {str(e)}"
        )
