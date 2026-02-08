"""
PDF generation API routes
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer

logger = logging.getLogger(__name__)

from app.models.pdf_models import (
    PDFGenerationRequest,
    PDFGenerationFromFileRequest,
    PDFGenerationResponse,
    ErrorResponse,
    HealthCheckResponse,
    SimpleStorybookRequest,
    KDPStorybookRequest,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStatusResponse,
    CleanupResponse
)
from app.services.pdf_service import PDFService
from app.services.video_service import VideoGenerationService

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
            from_string=True,
            stories=request.stories
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


@router.post(
    "/generate-storybook-enhanced",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate Children's Storybook PDF", 
    description="""
    Generate a comprehensive children's storybook PDF with enhanced features.
    **Uses the SAME request format as /pdf/generate endpoint.**
    
    Perfect for Amazon KDP publishing. Creates:
    - **Title page** with auto-generated metadata
    - **Story pages** with text and auto-generated illustration prompts  
    - **Professional formatting** optimized for children's books
    
    **Request Format (identical to /pdf/generate):**
    ```json
    {
      "html_content": "<!DOCTYPE html>...",
      "stories": [
        {"page_number": 1, "text": "Once upon a time..."},
        {"page_number": 2, "text": "The adventure continues..."}
      ],
      "filename": "my_storybook"
    }
    ```
    
    The endpoint automatically generates illustration prompts for each page based on the story text.
    """,
    responses={
        201: {
            "description": "Storybook PDF generated successfully",
            "model": PDFGenerationResponse
        },
        400: {
            "description": "Invalid request data",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during PDF generation",
            "model": ErrorResponse
        }
    }
)
async def generate_storybook_pdf(
    request: PDFGenerationRequest,  # Use same model as /generate endpoint
    token: Optional[str] = Depends(security)
):
    """
    Generate a professional children's storybook PDF suitable for Amazon KDP publishing.
    
    Uses the same request format as /generate but creates an enhanced storybook with:
    - Title page featuring metadata (auto-generated from filename)
    - Individual story pages with text and illustration prompts  
    - Professional layout optimized for children's book publishing
    
    Args:
        request: PDFGenerationRequest (same as /generate endpoint)
        token: Optional authentication token
        
    Returns:
        PDFGenerationResponse: Success response with download details
        
    Raises:
        HTTPException: If PDF generation fails or invalid data provided
    """
    try:
        # Use the same format as /generate endpoint with html_content and stories
        from app.models.pdf_models import BookMetadata, StorybookPage
        
        # Extract basic info or use defaults
        title = request.filename or "Generated Storybook"
        
        # Create default metadata from request
        default_metadata = BookMetadata(
            title=title.replace("_", " ").title(),
            author="Generated Author",
            age_range="All Ages", 
            theme="Adventure and Learning",
            moral_lesson="Every story teaches us something new."
        )
        
        # Extract images from HTML content
        images = pdf_service._extract_images_from_html(request.html_content)
        
        # Convert stories to storybook pages
        stories = request.stories or []
        pages = []
        
        for i, story in enumerate(stories):
            page = StorybookPage(
                page_number=story.page_number,
                story_text=story.text,
                illustration_prompt=f"Illustration for page {story.page_number} - create a suitable children's book image based on the story text: {story.text[:100]}..."
            )
            
            # Attach image data if available for this page (use index-based mapping)
            if i < len(images):  # Use story index instead of page_number
                page.image_data = images[i]  # Map by order: first story gets first image, etc.
            
            pages.append(page)
        
        # If no stories provided, create a simple page from HTML content
        if not pages:
            pages = [StorybookPage(
                page_number=1,
                story_text="Welcome to your storybook!",
                illustration_prompt="A welcoming scene for a children's storybook, bright and colorful."
            )]
        
        filename = request.filename or "simple_storybook"
        
        # Generate the storybook PDF
        result = await pdf_service.generate_storybook_pdf(
            metadata=default_metadata,
            pages=pages,
            filename=filename
        )
        
        return PDFGenerationResponse(
            success=True,
            message="Storybook PDF generated successfully",
            filename=result["filename"],
            file_path=result["file_path"],
            download_url=f"/pdf/download/{result['filename']}"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate storybook PDF: {str(e)}"
        )


@router.post(
    "/generate-storybook-simple",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate Storybook from Simple Request", 
    description="""
    Generate a children's storybook PDF from simplified request format.
    
    Perfect for single-page story generation with external image URLs.
    
    **Request Format:**
    ```json
    {
      "pageNumber": 1,
      "text": "Kaya the Clever Kangaroo and the Problem-solving and creativity",
      "imageUrl": "https://drive.google.com/file/d/1zkXqckTWC6CyoPAGYsaULdttFzvXOhsg/view?usp=drivesdk",
      "filename": "kaya_kangaroo_story"
    }
    ```
    
    Features:
    - **Auto-downloads images** from URLs (including Google Drive)
    - **Professional children's book layout** with image and text
    - **Title page generation** from story content
    - **Optimized for Amazon KDP** publishing
    """,
    responses={
        201: {
            "description": "Storybook PDF generated successfully",
            "model": PDFGenerationResponse
        },
        400: {
            "description": "Invalid request data",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during PDF generation",
            "model": ErrorResponse
        }
    }
)
async def generate_simple_storybook_pdf(
    request: SimpleStorybookRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate a professional children's storybook PDF from simplified request.
    
    Downloads the image from the provided URL and creates a professional
    storybook layout with title page and story content.
    
    Args:
        request: SimpleStorybookRequest with pageNumber, text, imageUrl, and optional filename
        token: Optional authentication token
        
    Returns:
        PDFGenerationResponse: Success response with download details
        
    Raises:
        HTTPException: If PDF generation fails or invalid data provided
    """
    try:
        # Generate the simple storybook PDF
        result = await pdf_service.generate_simple_storybook_pdf(
            page_number=request.pageNumber,
            text=request.text,
            image_url=request.imageUrl,
            filename=request.filename
        )
        
        return PDFGenerationResponse(
            success=True,
            message="Simple storybook PDF generated successfully",
            filename=result["filename"],
            file_path=result["file_path"],
            download_url=f"/pdf/download/{result['filename']}"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate simple storybook PDF: {str(e)}"
        )


@router.post(
    "/generate-kdp-storybook",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate KDP-Ready Children's Storybook PDF", 
    description="""
    Generate a professional children's storybook PDF optimized for Amazon KDP publishing.
    
    Supports different page types with appropriate layouts:
    - **Cover pages**: Prominent title overlaid on cover image
    - **Story pages**: Text overlaid on illustrations with adjustable transparency
    - **End pages**: "The End" and moral lesson overlaid on images
    
    **Request Format:**
    ```json
    {
      "pages": [
        {
          "page_number": 1,
          "page_type": "cover",
          "text": "The Adventures of Kaya the Kangaroo",
          "image_url": "https://example.com/cover.jpg"
        },
        {
          "page_number": 2,
          "page_type": "story",
          "text": "Once upon a time, in a magical forest...",
          "image_url": "https://example.com/story1.jpg"
        },
        {
          "page_number": 3,
          "page_type": "end",
          "text": "Always be kind and help others in need.",
          "image_url": "https://example.com/end.jpg"
        }
      ],
      "filename": "kaya_adventures",
      "text_overlay_opacity": 0.7
    }
    ```
    
    Features:
    - **Square format** (8.5" x 8.5") perfect for children's books
    - **High-quality** 300 DPI for print
    - **Child-friendly fonts** (26-34pt) Georgia/serif with proper margins
    - **Fluffy cloud-shaped text overlays** with organic, whimsical design
    - **Semi-transparent clouds** (40-60% opacity) showing background watercolor scenes
    - **Asymmetrical cloud puffs** for natural, dreamy storybook aesthetic
    - **Subtle drop shadows** (0, 3, 12px) for depth and dimension
    - **Auto-downloads and resizes images** maintaining aspect ratio
    - **Professional text positioning** with generous padding inside cloud boundaries
    """,
    responses={
        201: {
            "description": "KDP storybook PDF generated successfully",
            "model": PDFGenerationResponse
        },
        400: {
            "description": "Invalid request data",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during PDF generation",
            "model": ErrorResponse
        }
    }
)
async def generate_kdp_storybook_pdf(
    request: KDPStorybookRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate a professional KDP-ready children's storybook PDF.
    
    Creates a complete storybook with different page types:
    - Cover pages with prominent titles and cover images
    - Story pages with readable text and illustrations
    - End pages with moral lessons and decorative elements
    
    Args:
        request: KDPStorybookRequest with array of pages and optional filename
        token: Optional authentication token
        
    Returns:
        PDFGenerationResponse: Success response with download details
        
    Raises:
        HTTPException: If PDF generation fails or invalid data provided
    """
    try:
        # Generate the KDP storybook PDF
        result = await pdf_service.generate_kdp_storybook_pdf(
            pages=request.pages,
            filename=request.filename,
            text_overlay_opacity=request.text_overlay_opacity,
            page_width=request.page_width,
            page_height=request.page_height,
            title_color=request.title_color,
            title_font_size=request.title_font_size,
            text_font_size=request.text_font_size,
            text_color=request.text_color
        )
        
        return PDFGenerationResponse(
            success=True,
            message="KDP storybook PDF generated successfully",
            filename=result["filename"],
            file_path=result["file_path"],
            download_url=f"/pdf/download/{result['filename']}"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate KDP storybook PDF: {str(e)}"
        )


@router.post(
    "/generate-kdp-storybook-from-images",
    response_model=PDFGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate KDP Storybook PDF (Image-Driven)",
    description="""
    Generate a KDP-ready children's storybook PDF **driven primarily by images**.

    This endpoint accepts the **same request format** as `/generate-kdp-storybook`
    and uses the provided `image_url` values to build the book. It also respects
    the `printtitle` flag on cover pages:

    - `printtitle: true`  → cover title is rendered using the `text` field
    - `printtitle: false` → cover title is **not** rendered; only the image is used

    Example request:

    ```json
    {
      "pages": [
        {
          "page_number": 0,
          "page_type": "cover",
          "text": "Bella the Brave Bunny's Big Adventure",
          "image_url": "https://example.com/cover.jpg",
          "printtitle": false
        },
        {
          "page_number": 1,
          "page_type": "story",
          "text": "Once upon a time...",
          "image_url": "https://example.com/page1.jpg"
        }
      ],
      "filename": "bella_the_brave_bunnys_big_adventure",
      "text_overlay_opacity": 0.6,
      "page_width": 2550,
      "page_height": 2550,
      "title_color": "#FFFFFF",
      "title_font_size": 200,
      "text_font_size": 250,
      "text_color": "#2C2C2C"
    }
    ```
    """,
    responses={
        201: {
            "description": "Image-driven KDP storybook PDF generated successfully",
            "model": PDFGenerationResponse
        },
        400: {
            "description": "Invalid request data",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error during PDF generation",
            "model": ErrorResponse
        }
    }
)
async def generate_kdp_storybook_pdf_from_images(
    request: KDPStorybookRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate a KDP-ready storybook PDF primarily based on the provided images.

    Uses the same `KDPStorybookRequest` as `/generate-kdp-storybook` and reuses
    the same underlying PDF generation logic. The only behavioral difference is
    semantic: this endpoint is intended for flows where the **images are primary**
    and the cover title may optionally be hidden via `printtitle: false`.
    """
    try:
        result = await pdf_service.generate_kdp_storybook_pdf(
            pages=request.pages,
            filename=request.filename,
            text_overlay_opacity=request.text_overlay_opacity,
            page_width=request.page_width,
            page_height=request.page_height,
            title_color=request.title_color,
            title_font_size=request.title_font_size,
            text_font_size=request.text_font_size,
            text_color=request.text_color
        )

        return PDFGenerationResponse(
            success=True,
            message="Image-driven KDP storybook PDF generated successfully",
            filename=result["filename"],
            file_path=result["file_path"],
            download_url=f"/pdf/download/{result['filename']}"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate image-driven KDP storybook PDF: {str(e)}"
        )


@router.post("/generate-video", response_model=VideoGenerationResponse)
async def generate_video_from_pdf(
    request: VideoGenerationRequest,
    token: Optional[str] = Depends(security)
):
    """
    Generate video from PDF with text-to-speech narration
    
    This endpoint converts a PDF file to a video with voice narration for each page.
    Supports both regular text-to-speech and voice cloning.
    
    Args:
        request: Video generation request with PDF path, page texts, and options
        token: Optional authentication token
        
    Returns:
        VideoGenerationResponse: Success status and video file information
        
    Raises:
        HTTPException: If video generation fails or dependencies not available
    """
    try:
        # Check if video dependencies are available
        try:
            video_service = VideoGenerationService()
        except ImportError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Video generation dependencies not available: {str(e)}"
            )
        
        # Validate PDF file exists
        if not os.path.exists(request.pdf_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PDF file not found: {request.pdf_path}"
            )
        
        # Generate output filename if not provided
        output_filename = request.output_filename
        if not output_filename:
            pdf_name = os.path.splitext(os.path.basename(request.pdf_path))[0]
            output_filename = f"{pdf_name}_video"
        
        # Add .mp4 extension if not present
        if not output_filename.endswith('.mp4'):
            output_filename += '.mp4'
        
        # Create output directory if it doesn't exist
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_filename)

        request.voice_file = "/Users/arunakumara/git/pdf-generator/voice/story_voice.mp3"
        
        # Generate video based on whether voice file is provided
        if request.voice_file and os.path.exists(request.voice_file):
            # Use voice cloning
            result = video_service.generate_video_with_voice_clone(
                pdf_path=request.pdf_path,
                page_texts=request.page_texts,
                voice_file=request.voice_file,
                output_file=output_path,
                fps=request.fps
            )
        else:
            # Use regular text-to-speech
            result = video_service.generate_video_with_tts(
                pdf_path=request.pdf_path,
                page_texts=request.page_texts,
                output_file=output_path,
                language=request.language,
                fps=request.fps,
                skip_cover_page=request.skip_cover_page
            )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Video generation failed: {result.get('error', 'Unknown error')}"
            )
        
        return VideoGenerationResponse(
            success=True,
            message="Video generated successfully",
            filename=output_filename,
            file_path=result["file_path"],
            download_url=f"/pdf/download/{output_filename}",
            duration_seconds=result.get("duration_seconds")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate video: {str(e)}"
        )


@router.get(
    "/video/status/{filename}",
    response_model=VideoStatusResponse,
    summary="Check Video Status",
    description="Check the status and details of a generated video file"
)
async def check_video_status(
    filename: str,
    token: Optional[str] = Depends(security)
):
    """
    Check the status of a video file
    
    Args:
        filename: Name of the video file to check
        token: Optional authentication token
        
    Returns:
        VideoStatusResponse: Status information about the video file
    """
    try:
        # Sanitize filename
        import re
        safe_filename = re.sub(r'[^\w\-_.]', '_', filename)
        if not safe_filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename"
            )
        
        # Ensure .mp4 extension
        if not safe_filename.endswith('.mp4'):
            safe_filename += '.mp4'
        
        # Check if file exists in output directory
        output_dir = "output"
        file_path = os.path.join(output_dir, safe_filename)
        file_exists = os.path.exists(file_path)
        
        response_data = {
            "success": True,
            "message": "Video status retrieved successfully",
            "filename": safe_filename,
            "file_path": file_path,
            "exists": file_exists,
            "download_url": f"/pdf/download/{safe_filename}"
        }
        
        if file_exists:
            # Get file size
            file_size = os.path.getsize(file_path)
            response_data["file_size"] = file_size
            
            # Try to get video duration using moviepy
            try:
                from moviepy.editor import VideoFileClip
                with VideoFileClip(file_path) as video:
                    duration = video.duration
                    response_data["duration_seconds"] = duration
            except Exception:
                # If we can't get duration, just skip it
                pass
        
        return VideoStatusResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check video status: {str(e)}"
        )


@router.get(
    "/download/{filename}",
    summary="Download Video",
    description="Download a generated video file"
)
async def download_video(
    filename: str,
    token: Optional[str] = Depends(security)
):
    """
    Download a video file
    
    Args:
        filename: Name of the video file to download
        token: Optional authentication token
        
    Returns:
        FileResponse: The video file for download
    """
    try:
        # Sanitize filename
        import re
        safe_filename = re.sub(r'[^\w\-_.]', '_', filename)
        if not safe_filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename"
            )
        
        # Ensure .mp4 extension
        if not safe_filename.endswith('.mp4'):
            safe_filename += '.mp4'
        
        # Check if file exists in output directory
        output_dir = "output"
        file_path = os.path.join(output_dir, safe_filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video file not found: {safe_filename}"
            )
        
        # Return the file for download
        return FileResponse(
            path=file_path,
            filename=safe_filename,
            media_type="video/mp4"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download video: {str(e)}"
        )


@router.delete(
    "/cleanup",
    response_model=CleanupResponse,
    summary="Cleanup Output Files",
    description="Delete all generated output files (PDFs and videos) from the output directory"
)
async def cleanup_output_files(
    token: Optional[str] = Depends(security)
):
    """
    Clean up all generated output files
    
    This endpoint deletes all PDF and video files from the output directory.
    Useful for freeing up disk space or starting fresh.
    
    Args:
        token: Optional authentication token
        
    Returns:
        CleanupResponse: Summary of deleted files
    """
    try:
        import glob
        
        output_dir = "output"
        if not os.path.exists(output_dir):
            return CleanupResponse(
                success=True,
                message="Output directory does not exist, nothing to clean",
                files_deleted=0,
                total_size_bytes=0,
                deleted_files=[],
                file_types={}
            )
        
        # Find all files in output directory (excluding directories)
        all_files = []
        for file_path in glob.glob(os.path.join(output_dir, "*")):
            if os.path.isfile(file_path):
                all_files.append(file_path)
        
        if not all_files:
            return CleanupResponse(
                success=True,
                message="No files found in output directory",
                files_deleted=0,
                total_size_bytes=0,
                deleted_files=[],
                file_types={}
            )
        
        # Track deleted files
        deleted_files = []
        total_size = 0
        file_types_count = {}
        
        # Delete each file
        for file_path in all_files:
            try:
                # Get file info before deletion
                file_size = os.path.getsize(file_path)
                filename = os.path.basename(file_path)
                
                # Determine file type
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext == '.pdf':
                    file_type = 'pdf'
                elif file_ext in ['.mp4', '.avi', '.mov', '.mkv']:
                    file_type = 'video'
                elif file_ext in ['.mp3', '.wav', '.aac']:
                    file_type = 'audio'
                elif file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                    file_type = 'image'
                else:
                    file_type = 'other'
                
                # Count by type
                file_types_count[file_type] = file_types_count.get(file_type, 0) + 1
                
                # Delete the file
                os.remove(file_path)
                
                deleted_files.append(filename)
                total_size += file_size
                
            except Exception as file_error:
                # Log error but continue with other files
                logger.warning(f"Failed to delete {file_path}: {file_error}")
        
        # Clean up temporary files (e.g., MoviePy temp files)
        temp_files = glob.glob(os.path.join(output_dir, "*TEMP_*"))
        for temp_file in temp_files:
            try:
                if os.path.isfile(temp_file):
                    temp_size = os.path.getsize(temp_file)
                    os.remove(temp_file)
                    total_size += temp_size
                    file_types_count['temp'] = file_types_count.get('temp', 0) + 1
            except Exception:
                pass
        
        return CleanupResponse(
            success=True,
            message=f"Successfully cleaned up {len(deleted_files)} file(s)",
            files_deleted=len(deleted_files),
            total_size_bytes=total_size,
            deleted_files=sorted(deleted_files),
            file_types=file_types_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup output files: {str(e)}"
        )
