"""
Pydantic models for PDF generation API
"""
from typing import Optional
from pydantic import BaseModel, Field, validator
import re


class PDFGenerationRequest(BaseModel):
    """Request model for PDF generation from HTML string"""
    
    html_content: str = Field(
        ..., 
        description="HTML content to convert to PDF",
        min_length=1,
        example="<html><body><h1>Hello World</h1><p>This is a test PDF.</p></body></html>"
    )
    filename: Optional[str] = Field(
        None,
        description="Custom filename for the PDF (without extension)",
        max_length=100,
        example="my_document"
    )
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename to ensure it's safe"""
        if v is not None:
            # Remove any potentially dangerous characters
            v = re.sub(r'[^\w\-_.]', '_', v)
            if not v:
                raise ValueError('Filename cannot be empty after sanitization')
        return v


class PDFGenerationFromFileRequest(BaseModel):
    """Request model for PDF generation from HTML file"""
    
    html_file_path: str = Field(
        ...,
        description="Path to HTML file to convert to PDF",
        example="/path/to/file.html"
    )
    filename: Optional[str] = Field(
        None,
        description="Custom filename for the PDF (without extension)",
        max_length=100,
        example="my_document"
    )
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename to ensure it's safe"""
        if v is not None:
            # Remove any potentially dangerous characters
            v = re.sub(r'[^\w\-_.]', '_', v)
            if not v:
                raise ValueError('Filename cannot be empty after sanitization')
        return v


class PDFGenerationResponse(BaseModel):
    """Response model for PDF generation"""
    
    success: bool = Field(..., description="Whether the PDF was generated successfully")
    message: str = Field(..., description="Success or error message")
    filename: str = Field(..., description="Generated PDF filename")
    file_path: str = Field(..., description="Full path to the generated PDF file")
    download_url: str = Field(..., description="URL to download the generated PDF")


class ErrorResponse(BaseModel):
    """Error response model"""
    
    success: bool = Field(False, description="Always false for error responses")
    message: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code if available")


class HealthCheckResponse(BaseModel):
    """Health check response model"""
    
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Health check message")
    version: str = Field(..., description="API version")
