"""
Pydantic models for PDF generation API
"""
from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re


class Story(BaseModel):
    """Model for individual story page"""
    
    page_number: int = Field(
        ..., 
        description="Page number for this story",
        ge=1,
        example=1
    )
    text: str = Field(
        ..., 
        description="Text content for this page",
        min_length=1,
        example="Once upon a time, in a magical forest..."
    )


class StorybookPage(BaseModel):
    """Enhanced model for children's storybook pages with illustration prompts"""
    
    page_number: int = Field(
        ..., 
        description="Page number for this story page",
        ge=1,
        example=1
    )
    story_text: str = Field(
        ..., 
        description="Story text content for this page (simple, engaging sentences for kids)",
        min_length=1,
        example="In a peaceful forest, Bella the bunny dreamed of grand adventures."
    )
    illustration_prompt: str = Field(
        ...,
        description="Clear image description for illustrator/AI with consistent art style",
        min_length=1,
        example="A small, curious bunny sitting under a big oak tree, watercolor style, bright and cheerful."
    )
    image_data: Optional[str] = Field(
        None,
        description="Optional image data (base64 or URL) to use for illustration"
    )
    
    class Config:
        extra = "allow"  # Allow additional fields for flexibility


class BookMetadata(BaseModel):
    """Metadata for children's storybook"""
    
    title: str = Field(
        ...,
        description="Main title of the storybook",
        min_length=1,
        max_length=100,
        example="Bella the Brave Bunny"
    )
    subtitle: Optional[str] = Field(
        None,
        description="Optional subtitle",
        max_length=100,
        example="A Story of Courage and Kindness"
    )
    author: str = Field(
        ...,
        description="Author name",
        min_length=1,
        max_length=100,
        example="Jane Doe"
    )
    age_range: str = Field(
        ...,
        description="Target age range for the book",
        example="4-7 years"
    )
    theme: str = Field(
        ...,
        description="Main theme of the story",
        min_length=1,
        max_length=200,
        example="courage and kindness"
    )
    moral_lesson: str = Field(
        ...,
        description="The moral lesson or message of the story",
        min_length=1,
        max_length=200,
        example="Even the smallest can be brave."
    )


class StorybookRequest(BaseModel):
    """Request model for generating comprehensive children's storybook PDFs"""
    
    metadata: BookMetadata = Field(
        ...,
        description="Book metadata including title, author, theme, etc."
    )
    pages: List[StorybookPage] = Field(
        ...,
        description="List of storybook pages with text and illustration prompts",
        min_items=1,
        max_items=50  # Reasonable limit for children's books
    )
    filename: Optional[str] = Field(
        None,
        description="Custom filename for the PDF (without extension)",
        max_length=100,
        example="bella_the_brave_bunny"
    )
    
    @validator('pages')
    def validate_pages_sequence(cls, v):
        """Ensure page numbers are sequential starting from 1"""
        if not v:
            return v
        
        page_numbers = [page.page_number for page in v]
        expected_numbers = list(range(1, len(v) + 1))
        
        if sorted(page_numbers) != expected_numbers:
            raise ValueError('Page numbers must be sequential starting from 1')
        
        return v
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename to ensure it's safe"""
        if v is not None:
            # Remove any potentially dangerous characters
            v = re.sub(r'[^\w\-_.]', '_', v)
            if not v:
                raise ValueError('Filename cannot be empty after sanitization')
        return v


class PDFGenerationRequest(BaseModel):
    """Request model for PDF generation from HTML string"""
    
    html_content: str = Field(
        ..., 
        description="HTML content to convert to PDF",
        min_length=1,
        example="<html><body><h1>Hello World</h1><p>This is a test PDF.</p></body></html>"
    )
    stories: Optional[List[Story]] = Field(
        None,
        description="Array of stories with page numbers and text content",
        example=[
            {"page_number": 1, "text": "Once upon a time..."},
            {"page_number": 2, "text": "The adventure continues..."}
        ]
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


class SimpleStorybookRequest(BaseModel):
    """Simplified request model for single-page storybook generation"""
    
    pageNumber: int = Field(
        ...,
        description="Page number for this story",
        ge=1,
        example=1
    )
    text: str = Field(
        ...,
        description="Story text content for this page",
        min_length=1,
        example="Kaya the Clever Kangaroo and the Problem-solving and creativity"
    )
    imageUrl: str = Field(
        ...,
        description="URL to the illustration image for this page",
        example="https://drive.google.com/file/d/1zkXqckTWC6CyoPAGYsaULdttFzvXOhsg/view?usp=drivesdk"
    )
    filename: Optional[str] = Field(
        None,
        description="Custom filename for the PDF (without extension)",
        max_length=100,
        example="kaya_kangaroo_story"
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


class KDPStorybookPage(BaseModel):
    """Model for KDP storybook pages with different page types"""
    
    page_number: int = Field(
        ...,
        description="Page number for this page (0 for cover, 1+ for content)",
        ge=0,
        example=0
    )
    page_type: str = Field(
        ...,
        description="Type of page: cover, story, or end",
        pattern="^(cover|story|end)$",
        example="cover"
    )
    text: str = Field(
        ...,
        description="Text content for this page",
        min_length=1,
        example="The Adventures of Kaya the Kangaroo"
    )
    image_url: str = Field(
        ...,
        description="URL of the image for this page",
        example="https://example.com/image.jpg"
    )
    image_data: Optional[str] = Field(
        None,
        description="Downloaded image data (base64) - populated automatically"
    )
    # Cover page specific fields (DEPRECATED - not used in current design)
    # The cover now uses only the 'text' field for the title in a colorful cloud bubble
    author: Optional[str] = Field(
        None,
        description="[DEPRECATED] Author name - not currently displayed on cover",
        max_length=100
    )
    subtitle: Optional[str] = Field(
        None,
        description="[DEPRECATED] Subtitle - not currently displayed on cover",
        max_length=200
    )
    age_range: Optional[str] = Field(
        None,
        description="[DEPRECATED] Age range - not currently displayed on cover",
        max_length=20
    )
    publisher: Optional[str] = Field(
        None,
        description="[DEPRECATED] Publisher - not currently displayed on cover",
        max_length=50
    )
    
    class Config:
        extra = "allow"  # Allow additional fields for flexibility


class KDPStorybookRequest(BaseModel):
    """Request model for KDP storybook generation"""
    
    pages: List[KDPStorybookPage] = Field(
        ...,
        description="Array of pages for the storybook",
        min_items=1,
        max_items=50
    )
    filename: Optional[str] = Field(
        None,
        description="Custom filename for the PDF (without extension)",
        max_length=100,
        example="my_storybook"
    )
    text_overlay_opacity: Optional[float] = Field(
        0.7,
        description="Text overlay background opacity (0.0-1.0)",
        ge=0.0,
        le=1.0,
        example=0.7
    )
    
    @validator('pages')
    def validate_pages_sequence(cls, v):
        """Ensure page numbers are sequential and have required page types"""
        if not v:
            return v
        
        # Check for sequential page numbers starting from 0
        page_numbers = [page.page_number for page in v]
        expected_numbers = list(range(0, len(v)))  # Start from 0
        
        if sorted(page_numbers) != expected_numbers:
            raise ValueError('Page numbers must be sequential starting from 0 (cover page should be 0)')
        
        # Check for at least one cover page
        page_types = [page.page_type for page in v]
        if 'cover' not in page_types:
            raise ValueError('At least one page must be of type "cover"')
        
        return v
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename to ensure it's safe"""
        if v is not None:
            # Remove any potentially dangerous characters
            v = re.sub(r'[^\w\-_.]', '_', v)
            if not v:
                raise ValueError('Filename cannot be empty after sanitization')
        return v


class HealthCheckResponse(BaseModel):
    """Health check response model"""
    
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Health check message")
    version: str = Field(..., description="API version")
