"""
PDF generation service using ReportLab
"""
import os
import uuid
import io
import base64
import re
import requests
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from fastapi import HTTPException
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PDFService:
    """Service class for PDF generation operations"""
    
    def __init__(self, output_dir: str = "output"):
        """
        Initialize PDF service
        
        Args:
            output_dir: Directory to store generated PDFs
        """
        self.output_dir = output_dir
        self.custom_font_available = False
        self._ensure_output_dir()
        
        # Register custom fonts
        self._register_custom_fonts()
    
    def _ensure_output_dir(self) -> None:
        """Ensure output directory exists"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def _register_custom_fonts(self):
        """Use consistent built-in font for all text"""
        # Use Times-Bold for all text consistently
        self.custom_font_available = False
        logger.info("Using built-in Times-Bold font consistently across all pages")
    
    def _download_image_from_url(self, image_url: str) -> Optional[bytes]:
        """
        Download image from URL, with special handling for Google Drive URLs
        
        Args:
            image_url: The URL of the image to download
            
        Returns:
            bytes: The image data if successful, None otherwise
        """
        try:
            # Handle Google Drive URLs with multiple methods
            if "drive.google.com" in image_url:
                # Extract file ID from Google Drive sharing URL
                if "/file/d/" in image_url:
                    file_id = image_url.split('/file/d/')[1].split('/')[0]
                    
                    # Try multiple Google Drive download methods with session handling
                    download_urls = [
                        f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
                        f"https://drive.google.com/uc?id={file_id}&export=download&confirm=t",
                        f"https://docs.google.com/uc?export=download&id={file_id}&confirm=t",
                        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
                        f"https://lh3.googleusercontent.com/d/{file_id}",  # Alternative Google hosting
                        f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000-h1000"  # Thumbnail endpoint
                    ]
                    
                    for url in download_urls:
                        logger.info(f"Trying Google Drive URL: {url}")
                        result = self._try_download_image_with_session(url, file_id)
                        if result:
                            return result
                    
                    logger.warning(f"All Google Drive download methods failed for file ID: {file_id}")
                    logger.warning(f"The Google Drive file may not be publicly accessible. Please ensure the file is shared with 'Anyone with the link can view' permission.")
                    return None
            else:
                # Regular URL download
                return self._try_download_image(image_url)
            
        except Exception as e:
            logger.error(f"Error processing image URL {image_url}: {str(e)}")
            return None
    
    def _try_download_image_with_session(self, url: str, file_id: str = None) -> Optional[bytes]:
        """
        Try to download an image using a session with better Google Drive handling
        
        Args:
            url: The URL to download from
            file_id: Google Drive file ID (for special handling)
            
        Returns:
            bytes: The image data if successful, None otherwise
        """
        try:
            session = requests.Session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site'
            }
            
            # First request to handle any redirects or confirmation pages
            response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
            
            # Check if this is a Google Drive confirmation page (for large files)
            if "drive.google.com" in url and "confirm" in response.text:
                logger.info(f"Handling Google Drive confirmation page for file {file_id}")
                
                # Look for download link in the confirmation page
                import re
                download_link_match = re.search(r'href="(/uc\?export=download[^"]*)"', response.text)
                if download_link_match:
                    confirmation_url = "https://drive.google.com" + download_link_match.group(1).replace('&amp;', '&')
                    logger.info(f"Found confirmation download link: {confirmation_url}")
                    response = session.get(confirmation_url, headers=headers, timeout=30, allow_redirects=True)
            
            response.raise_for_status()
            
            # Check if we got an image by examining the content
            image_data = response.content
            content_type = response.headers.get('content-type', '').lower()
            
            # First check content type
            if content_type.startswith('image/'):
                logger.info(f"Downloaded image: {len(image_data)} bytes, type: {content_type}")
                return image_data
            
            # Then check by file signature (magic bytes)
            if len(image_data) > 4 and (
                image_data.startswith(b'\xff\xd8\xff') or  # JPEG
                image_data.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
                image_data.startswith(b'GIF89a') or       # GIF89a
                image_data.startswith(b'GIF87a') or       # GIF87a
                image_data.startswith(b'RIFF') and b'WEBP' in image_data[:20] or  # WebP
                image_data.startswith(b'\x00\x00\x01\x00') or  # ICO
                image_data.startswith(b'BM')  # BMP
            ):
                logger.info(f"Downloaded image (detected by signature): {len(image_data)} bytes")
                return image_data
            
            # If content is HTML and small, it might be an error page
            if 'text/html' in content_type and len(image_data) < 10000:
                logger.warning(f"Received HTML error page from {url}: {image_data[:200].decode('utf-8', errors='ignore')}")
                return None
            
            # If content is HTML but large, might be a login/permission page
            if 'text/html' in content_type:
                logger.warning(f"Received HTML instead of image from {url} - file may not be publicly accessible")
                return None
            
            logger.warning(f"Downloaded content doesn't appear to be an image: {content_type}, size: {len(image_data)}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download from {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error downloading from {url}: {str(e)}")
            return None

    def _try_download_image(self, url: str) -> Optional[bytes]:
        """
        Try to download an image from a specific URL
        
        Args:
            url: The URL to download from
            
        Returns:
            bytes: The image data if successful, None otherwise
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            # Check if we got an image by examining the content
            image_data = response.content
            content_type = response.headers.get('content-type', '').lower()
            
            # First check content type
            if content_type.startswith('image/'):
                logger.info(f"Downloaded image: {len(image_data)} bytes, type: {content_type}")
                return image_data
            
            # Then check by file signature (magic bytes)
            if len(image_data) > 0 and (
                image_data.startswith(b'\xff\xd8\xff') or  # JPEG
                image_data.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
                image_data.startswith(b'GIF89a') or       # GIF89a
                image_data.startswith(b'GIF87a') or       # GIF87a
                image_data.startswith(b'RIFF') and b'WEBP' in image_data[:20]  # WebP
            ):
                logger.info(f"Downloaded image (detected by signature): {len(image_data)} bytes")
                return image_data
            
            # If content is HTML, it might be a Google Drive preview page
            if 'text/html' in content_type:
                logger.warning(f"Received HTML instead of image from {url}")
                return None
            
            logger.warning(f"Downloaded content doesn't appear to be an image: {content_type}, size: {len(image_data)}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download from {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error downloading from {url}: {str(e)}")
            return None
    
    def _create_cloud_text_overlay(self, background_image_data: bytes, text: str, 
                                  font_size: int = 28, opacity: float = 0.7,
                                  position: str = "top") -> bytes:
        """
        Create a cloud-shaped text overlay using Pillow with semi-transparent background
        
        Args:
            background_image_data: The background image as bytes
            text: Text to overlay
            font_size: Font size for the text
            opacity: Opacity for the cloud background (0.0-1.0)
            position: Position of the overlay ("top", "center", "bottom")
            
        Returns:
            bytes: The composite image with cloud text overlay
        """
        try:
            # Load background image
            bg_image = Image.open(io.BytesIO(background_image_data))
            bg_image = bg_image.convert("RGBA")
            
            # Create a new image for the overlay
            overlay = Image.new("RGBA", bg_image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            # Try to load a system font, fallback to default
            try:
                # Try to find a bold font
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except:
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
            
            # Calculate text dimensions and wrapping
            words = text.split()
            lines = []
            current_line = []
            max_width = bg_image.width * 0.8  # 80% of image width
            
            for word in words:
                test_line = " ".join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                text_width = bbox[2] - bbox[0]
                
                if text_width <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)
            
            if current_line:
                lines.append(" ".join(current_line))
            
            # Limit to 4 lines maximum
            lines = lines[:4]
            
            # Calculate total text area dimensions
            line_height = font_size + 8
            total_text_height = len(lines) * line_height
            max_text_width = max([draw.textbbox((0, 0), line, font=font)[2] - 
                                 draw.textbbox((0, 0), line, font=font)[0] for line in lines])
            
            # Calculate cloud dimensions (larger than text for padding)
            cloud_padding = 40
            cloud_width = max_text_width + cloud_padding * 2
            cloud_height = total_text_height + cloud_padding
            
            # Calculate position
            if position == "top":
                cloud_y = bg_image.height * 0.1
            elif position == "center":
                cloud_y = (bg_image.height - cloud_height) / 2
            else:  # bottom
                cloud_y = bg_image.height * 0.8 - cloud_height
            
            cloud_x = (bg_image.width - cloud_width) / 2
            
            # Create cloud shape using multiple ellipses
            cloud_alpha = int(230 * opacity)  # Semi-transparent white
            shadow_alpha = int(100 * opacity)  # Shadow
            
            # Draw drop shadow first (offset cloud)
            shadow_offset = 4
            self._draw_cloud_shape(draw, cloud_x + shadow_offset, cloud_y + shadow_offset, 
                                 cloud_width, cloud_height, (128, 128, 128, shadow_alpha))
            
            # Draw main cloud shape
            self._draw_cloud_shape(draw, cloud_x, cloud_y, cloud_width, cloud_height, 
                                 (255, 255, 255, cloud_alpha))
            
            # Draw text on the cloud
            text_start_y = cloud_y + (cloud_height - total_text_height) / 2
            
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = cloud_x + (cloud_width - text_width) / 2
                text_y = text_start_y + i * line_height
                
                # Draw text with dark color for contrast
                draw.text((text_x, text_y), line, font=font, fill=(50, 50, 50, 255))
            
            # Composite the overlay onto the background
            composite = Image.alpha_composite(bg_image, overlay)
            
            # Convert back to RGB for PDF
            final_image = composite.convert("RGB")
            
            # Save to bytes
            output_buffer = io.BytesIO()
            final_image.save(output_buffer, format="JPEG", quality=95)
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating cloud text overlay: {str(e)}")
            # Return original image if overlay creation fails
            return background_image_data
    
    def _create_fluffy_cloud_overlay(self, background_image_data: bytes, text: str, 
                                   font_size: int = 28, opacity: float = 0.5,
                                   position: str = "top", text_color: str = "#000000") -> bytes:
        """
        Create a fluffy, organic cloud-shaped text overlay using Pillow
        
        Args:
            background_image_data: The background image as bytes
            text: Text to overlay
            font_size: Font size for the text
            opacity: Opacity for the cloud background (0.0-1.0)
            position: Position of the cloud ("top", "center", "bottom")
            
        Returns:
            bytes: The composite image with fluffy cloud text overlay
        """
        try:
            from PIL import Image as PILImage
            # Load background image
            bg_image = PILImage.open(io.BytesIO(background_image_data))
            bg_image = bg_image.convert("RGBA")
            
            # Convert hex color to RGB tuple
            def hex_to_rgb(hex_color):
                hex_color = hex_color.strip().lstrip('#')
                if len(hex_color) == 6:
                    r = int(hex_color[0:2], 16)
                    g = int(hex_color[2:4], 16)
                    b = int(hex_color[4:6], 16)
                    return (r, g, b, 255)  # Add alpha channel
                return (0, 0, 0, 255)  # Default to black
            
            text_rgba = hex_to_rgb(text_color)
            
            # Create a new image for the overlay
            overlay = PILImage.new("RGBA", bg_image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            # Try to load a bold system font with serif preference
            try:
                # Try Georgia Bold first (serif, child-friendly, bold)
                font = ImageFont.truetype("/System/Library/Fonts/Georgia Bold.ttc", font_size)
            except:
                try:
                    # Fallback to Georgia (serif, child-friendly)
                    font = ImageFont.truetype("/System/Library/Fonts/Georgia.ttc", font_size)
                except:
                    try:
                        # Fallback to Times Bold (serif, bold)
                        font = ImageFont.truetype("/System/Library/Fonts/Times Bold.ttc", font_size)
                    except:
                        try:
                            # Fallback to Times (serif)
                            font = ImageFont.truetype("/System/Library/Fonts/Times.ttc", font_size)
                        except:
                            try:
                                # Fallback to Helvetica Bold (rounded sans-serif, bold)
                                font = ImageFont.truetype("/System/Library/Fonts/Helvetica Bold.ttc", font_size)
                            except:
                                try:
                                    # Fallback to Helvetica (rounded sans-serif)
                                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                                except:
                                    font = ImageFont.load_default()
            
            # Calculate text dimensions and wrapping with generous padding
            # First, split by explicit line breaks (\n) to preserve them
            explicit_lines = text.split('\n')
            lines = []
            
            # Cloud width: 75-85% of image width
            cloud_width = bg_image.width * 0.8
            # Generous padding: 35-45px on all sides
            text_padding = 40
            max_text_width = cloud_width - (text_padding * 2)
            
            # Wrap each explicit line separately
            for explicit_line in explicit_lines:
                if not explicit_line.strip():  # Empty line becomes blank line
                    lines.append("")
                    continue
                    
                words = explicit_line.split()
                current_line = []
                
                # Wrap words for this explicit line
                for word in words:
                    test_line = " ".join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    text_width = bbox[2] - bbox[0]
                    
                    if text_width <= max_text_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(" ".join(current_line))
                            current_line = [word]
                        else:
                            lines.append(word)
                
                # Add the last line from this explicit line
                if current_line:
                    lines.append(" ".join(current_line))
            
            # Limit lines based on position (more lines for center/end pages)
            max_lines = 6 if position == "center" else 4
            lines = lines[:max_lines]
            
            # Calculate total text area dimensions
            line_height = int(font_size * 1.5)  # 1.5 line height for comfortable reading
            total_text_height = len(lines) * line_height
            max_text_width_actual = max([draw.textbbox((0, 0), line, font=font)[2] - 
                                       draw.textbbox((0, 0), line, font=font)[0] for line in lines])
            
            # Calculate cloud dimensions with generous padding
            cloud_width = max_text_width_actual + text_padding * 2
            cloud_height = total_text_height + text_padding * 2
            
            # Ensure cloud doesn't exceed 85% of image width
            if cloud_width > bg_image.width * 0.85:
                cloud_width = bg_image.width * 0.85
            
            # Calculate position based on requirements
            if position == "top":
                # Place cloud at the very top of the page with minimal margin
                cloud_y = bg_image.height * 0.05  # Just 5% from the top edge
            elif position == "center":
                cloud_y = (bg_image.height - cloud_height) / 2
            else:  # bottom
                cloud_y = bg_image.height * 0.65 - cloud_height
            
            cloud_x = (bg_image.width - cloud_width) / 2
            
            # Create fluffy cloud with proper opacity (40-60% range)
            # Convert opacity to alpha value (102-153 out of 255)
            cloud_alpha = int(102 + (opacity * 51))  # Maps 0.0-1.0 to 102-153
            shadow_alpha = int(38)  # 15% opacity for shadow
            
            # Draw drop shadow first (subtle: 0, 3, 12, rgba(0,0,0,0.15))
            shadow_offset_x = 0
            shadow_offset_y = 3
            shadow_blur = 12
            self._draw_fluffy_cloud_shape(draw, cloud_x + shadow_offset_x, cloud_y + shadow_offset_y, 
                                        cloud_width, cloud_height, (0, 0, 0, shadow_alpha))
            
            # Draw main fluffy cloud shape (semi-transparent white)
            self._draw_fluffy_cloud_shape(draw, cloud_x, cloud_y, cloud_width, cloud_height, 
                                        (255, 255, 255, cloud_alpha))
            
            # Draw text inside the cloud with proper positioning
            text_start_x = cloud_x + text_padding
            text_start_y = cloud_y + text_padding + (cloud_height - total_text_height - text_padding * 2) / 2
            
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                # Center-align text horizontally within the cloud
                line_x = cloud_x + (cloud_width - text_width) / 2
                line_y = text_start_y + i * line_height
                
                # Draw text with subtle shadow for extra contrast
                shadow_x, shadow_y = line_x + 1, line_y + 1
                draw.text((shadow_x, shadow_y), line, font=font, fill=(0, 0, 0, 102))  # 40% shadow
                
                # Draw main text with custom color
                draw.text((line_x, line_y), line, font=font, fill=text_rgba)
            
            # Composite the overlay onto the background
            composite = PILImage.alpha_composite(bg_image, overlay)
            
            # Convert back to RGB for PDF
            final_image = composite.convert("RGB")
            
            # Save to bytes with high quality
            output_buffer = io.BytesIO()
            final_image.save(output_buffer, format="JPEG", quality=95)
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating fluffy cloud text overlay: {str(e)}")
            # Return original image if overlay creation fails
            return background_image_data
    
    def _draw_cloud_shape(self, draw: ImageDraw.Draw, x: float, y: float, 
                         width: float, height: float, color: tuple):
        """
        Draw a cloud shape using multiple overlapping ellipses
        
        Args:
            draw: ImageDraw object
            x, y: Top-left position of the cloud
            width, height: Dimensions of the cloud
            color: RGBA color tuple
        """
        # Main body ellipse
        main_width = width * 0.6
        main_height = height * 0.5
        main_x = x + width * 0.2
        main_y = y + height * 0.3
        
        draw.ellipse([main_x, main_y, main_x + main_width, main_y + main_height], fill=color)
        
        # Left puff
        left_size = height * 0.4
        left_x = x + width * 0.1
        left_y = y + height * 0.2
        draw.ellipse([left_x, left_y, left_x + left_size, left_y + left_size], fill=color)
        
        # Right puff
        right_size = height * 0.45
        right_x = x + width * 0.7
        right_y = y + height * 0.15
        draw.ellipse([right_x, right_y, right_x + right_size, right_y + right_size], fill=color)
        
        # Top puff
        top_size = height * 0.35
        top_x = x + width * 0.4
        top_y = y
        draw.ellipse([top_x, top_y, top_x + top_size, top_y + top_size], fill=color)
        
        # Bottom left puff
        bottom_left_size = height * 0.3
        bottom_left_x = x + width * 0.15
        bottom_left_y = y + height * 0.6
        draw.ellipse([bottom_left_x, bottom_left_y, 
                     bottom_left_x + bottom_left_size, bottom_left_y + bottom_left_size], fill=color)
        
        # Bottom right puff
        bottom_right_size = height * 0.32
        bottom_right_x = x + width * 0.65
        bottom_right_y = y + height * 0.65
        draw.ellipse([bottom_right_x, bottom_right_y, 
                     bottom_right_x + bottom_right_size, bottom_right_y + bottom_right_size], fill=color)
    
    def _draw_fluffy_cloud_shape(self, draw: ImageDraw.Draw, x: float, y: float, 
                                width: float, height: float, color: tuple):
        """
        Draw a fluffy, organic cloud shape with asymmetrical puffs for natural appearance
        
        Args:
            draw: ImageDraw object
            x, y: Top-left position of the cloud
            width, height: Dimensions of the cloud
            color: RGBA color tuple
        """
        # Main cloud body (large central rounded shape)
        main_width = width * 0.65
        main_height = height * 0.6
        main_x = x + width * 0.175
        main_y = y + height * 0.2
        
        draw.ellipse([main_x, main_y, main_x + main_width, main_y + main_height], fill=color)
        
        # Cloud puffs around perimeter (4-6 smaller rounded bumps)
        # Left side puff (larger)
        left_size_w = width * 0.35
        left_size_h = height * 0.45
        left_x = x + width * 0.05
        left_y = y + height * 0.25
        draw.ellipse([left_x, left_y, left_x + left_size_w, left_y + left_size_h], fill=color)
        
        # Right side puff (medium, asymmetrical)
        right_size_w = width * 0.4
        right_size_h = height * 0.38
        right_x = x + width * 0.6
        right_y = y + height * 0.18
        draw.ellipse([right_x, right_y, right_x + right_size_w, right_y + right_size_h], fill=color)
        
        # Top left puff (small, whimsical)
        top_left_size = min(width * 0.28, height * 0.32)
        top_left_x = x + width * 0.12
        top_left_y = y + height * 0.05
        draw.ellipse([top_left_x, top_left_y, top_left_x + top_left_size, top_left_y + top_left_size], fill=color)
        
        # Top right puff (medium, organic)
        top_right_size_w = width * 0.32
        top_right_size_h = height * 0.35
        top_right_x = x + width * 0.55
        top_right_y = y + height * 0.02
        draw.ellipse([top_right_x, top_right_y, top_right_x + top_right_size_w, top_right_y + top_right_size_h], fill=color)
        
        # Bottom left puff (small, soft)
        bottom_left_size_w = width * 0.25
        bottom_left_size_h = height * 0.28
        bottom_left_x = x + width * 0.08
        bottom_left_y = y + height * 0.65
        draw.ellipse([bottom_left_x, bottom_left_y, 
                     bottom_left_x + bottom_left_size_w, bottom_left_y + bottom_left_size_h], fill=color)
        
        # Bottom right puff (medium, dreamy)
        bottom_right_size_w = width * 0.3
        bottom_right_size_h = height * 0.32
        bottom_right_x = x + width * 0.65
        bottom_right_y = y + height * 0.68
        draw.ellipse([bottom_right_x, bottom_right_y, 
                     bottom_right_x + bottom_right_size_w, bottom_right_y + bottom_right_size_h], fill=color)
        
        # Additional small puffs for extra fluffiness
        # Top center small puff
        top_center_size = min(width * 0.18, height * 0.22)
        top_center_x = x + width * 0.35
        top_center_y = y + height * 0.08
        draw.ellipse([top_center_x, top_center_y, top_center_x + top_center_size, top_center_y + top_center_size], fill=color)
        
        # Bottom center small puff (asymmetrical)
        bottom_center_size_w = width * 0.22
        bottom_center_size_h = height * 0.25
        bottom_center_x = x + width * 0.4
        bottom_center_y = y + height * 0.75
        draw.ellipse([bottom_center_x, bottom_center_y, 
                     bottom_center_x + bottom_center_size_w, bottom_center_y + bottom_center_size_h], fill=color)
    
    def _parse_css(self, soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
        """
        Parse CSS from HTML and return a dictionary of styles
        
        Args:
            soup: BeautifulSoup object of the HTML
            
        Returns:
            Dict mapping selectors to style properties
        """
        css_styles = {}
        
        # Extract CSS from <style> tags
        for style_tag in soup.find_all('style'):
            css_text = style_tag.get_text()
            css_styles.update(self._parse_css_text(css_text))
        
        return css_styles
    
    def _parse_css_text(self, css_text: str) -> Dict[str, Dict[str, str]]:
        """
        Parse CSS text and return styles dictionary
        
        Args:
            css_text: CSS text content
            
        Returns:
            Dict mapping selectors to style properties
        """
        styles = {}
        
        # Remove comments
        css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
        
        # Split by rules
        rules = re.split(r'\{[^}]*\}', css_text)
        rule_blocks = re.findall(r'\{[^}]*\}', css_text)
        
        for i, rule in enumerate(rules):
            if i < len(rule_blocks):
                selectors = [s.strip() for s in rule.split(',') if s.strip()]
                properties = self._parse_css_properties(rule_blocks[i])
                
                for selector in selectors:
                    if selector not in styles:
                        styles[selector] = {}
                    styles[selector].update(properties)
        
        return styles
    
    def _parse_css_properties(self, rule_block: str) -> Dict[str, str]:
        """
        Parse CSS properties from a rule block
        
        Args:
            rule_block: CSS rule block like "{color: red; font-size: 12px;}"
            
        Returns:
            Dict of property: value pairs
        """
        properties = {}
        
        # Remove braces
        content = rule_block.strip('{}')
        
        # Split by semicolons
        declarations = [d.strip() for d in content.split(';') if d.strip()]
        
        for declaration in declarations:
            if ':' in declaration:
                prop, value = declaration.split(':', 1)
                properties[prop.strip()] = value.strip()
        
        return properties
    
    def _get_element_styles(self, element, css_styles: Dict[str, Dict[str, str]]) -> Dict[str, str]:
        """
        Get computed styles for an element
        
        Args:
            element: BeautifulSoup element
            css_styles: Parsed CSS styles
            
        Returns:
            Dict of computed style properties
        """
        styles = {}
        
        # Get inline styles first (highest priority)
        inline_style = element.get('style', '')
        if inline_style:
            inline_props = self._parse_css_properties(f"{{{inline_style}}}")
            styles.update(inline_props)
        
        # Apply CSS rules (lower priority)
        for selector, properties in css_styles.items():
            if self._selector_matches(element, selector):
                styles.update(properties)
        
        return styles
    
    def _selector_matches(self, element, selector: str) -> bool:
        """
        Check if a CSS selector matches an element
        
        Args:
            element: BeautifulSoup element
            selector: CSS selector string
            
        Returns:
            True if selector matches element
        """
        # Simple selector matching
        if selector == element.name:
            return True
        
        # Class selector
        if selector.startswith('.'):
            class_name = selector[1:]
            return class_name in element.get('class', [])
        
        # ID selector
        if selector.startswith('#'):
            id_name = selector[1:]
            return element.get('id') == id_name
        
        # Descendant selector (basic)
        if ' ' in selector:
            parts = selector.split()
            # For now, just check if the last part matches
            return self._selector_matches(element, parts[-1])
        
        return False
    
    def _parse_color(self, color_str: str) -> colors.Color:
        """
        Parse CSS color string to ReportLab color
        
        Args:
            color_str: CSS color string (hex, rgb, named)
            
        Returns:
            ReportLab color object
        """
        color_str = color_str.strip().lower()
        
        # Named colors
        named_colors = {
            'black': colors.black,
            'white': colors.white,
            'red': colors.red,
            'green': colors.green,
            'blue': colors.blue,
            'yellow': colors.yellow,
            'orange': colors.orange,
            'purple': colors.purple,
            'gray': colors.grey,
            'grey': colors.grey,
            'darkblue': colors.darkblue,
            'darkgreen': colors.darkgreen,
            'darkred': colors.darkred,
        }
        
        if color_str in named_colors:
            return named_colors[color_str]
        
        # Hex colors
        if color_str.startswith('#'):
            hex_color = color_str[1:]
            if len(hex_color) == 3:
                hex_color = ''.join([c*2 for c in hex_color])
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16) / 255.0
                g = int(hex_color[2:4], 16) / 255.0
                b = int(hex_color[4:6], 16) / 255.0
                return colors.Color(r, g, b)
        
        # RGB colors
        if color_str.startswith('rgb('):
            rgb_match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color_str)
            if rgb_match:
                r, g, b = [int(x) / 255.0 for x in rgb_match.groups()]
                return colors.Color(r, g, b)
        
        # Default to black
        return colors.black
    
    def _parse_font_size(self, font_size_str: str) -> float:
        """
        Parse CSS font size to points
        
        Args:
            font_size_str: CSS font size string
            
        Returns:
            Font size in points
        """
        if not font_size_str:
            return 12.0
        
        font_size_str = font_size_str.strip().lower()
        
        # Extract number and unit
        match = re.match(r'(\d+(?:\.\d+)?)(px|pt|em|rem|%)?', font_size_str)
        if not match:
            return 12.0
        
        value, unit = match.groups()
        value = float(value)
        
        # Convert to points
        if unit == 'px':
            return value * 0.75  # 1px ≈ 0.75pt
        elif unit == 'pt':
            return value
        elif unit == 'em' or unit == 'rem':
            return value * 12.0  # Assume 12pt base
        elif unit == '%':
            return (value / 100.0) * 12.0  # Assume 12pt base
        else:
            return value
    
    def _create_paragraph_style(self, name: str, parent_style, css_props: Dict[str, str]) -> ParagraphStyle:
        """
        Create a ParagraphStyle from CSS properties
        
        Args:
            name: Style name
            parent_style: Parent style to inherit from
            css_props: CSS properties dictionary
            
        Returns:
            ParagraphStyle object
        """
        style_kwargs = {}
        
        # Font size
        if 'font-size' in css_props:
            style_kwargs['fontSize'] = self._parse_font_size(css_props['font-size'])
        
        # Font weight
        if 'font-weight' in css_props:
            weight = css_props['font-weight'].lower()
            if weight in ['bold', 'bolder']:
                style_kwargs['fontName'] = 'Helvetica-Bold'
            elif weight in ['normal', 'lighter']:
                style_kwargs['fontName'] = 'Helvetica'
        
        # Font family
        if 'font-family' in css_props:
            font_family = css_props['font-family'].lower()
            if 'serif' in font_family or 'georgia' in font_family:
                style_kwargs['fontName'] = 'Times-Roman'
            elif 'monospace' in font_family or 'courier' in font_family:
                style_kwargs['fontName'] = 'Courier'
            else:
                style_kwargs['fontName'] = 'Helvetica'
        
        # Text color
        if 'color' in css_props:
            style_kwargs['textColor'] = self._parse_color(css_props['color'])
        
        # Background color
        if 'background-color' in css_props:
            style_kwargs['backColor'] = self._parse_color(css_props['background-color'])
        
        # Spacing
        if 'margin-top' in css_props or 'margin-bottom' in css_props:
            margin_top = self._parse_css_px(css_props.get('margin-top', '0'))
            margin_bottom = self._parse_css_px(css_props.get('margin-bottom', '0'))
            style_kwargs['spaceBefore'] = margin_top * 0.75  # Convert px to points
            style_kwargs['spaceAfter'] = margin_bottom * 0.75
        
        # Text alignment
        if 'text-align' in css_props:
            align = css_props['text-align'].lower()
            if align == 'center':
                style_kwargs['alignment'] = 1  # TA_CENTER
            elif align == 'right':
                style_kwargs['alignment'] = 2  # TA_RIGHT
            elif align == 'justify':
                style_kwargs['alignment'] = 4  # TA_JUSTIFY
        
        return ParagraphStyle(name, parent=parent_style, **style_kwargs)
    
    def _parse_css_px(self, value: str) -> float:
        """
        Parse CSS pixel value to points
        
        Args:
            value: CSS value string
            
        Returns:
            Value in points
        """
        if not value or value == '0':
            return 0.0
        
        match = re.match(r'(\d+(?:\.\d+)?)(px|pt|em|rem|%)?', value.strip().lower())
        if not match:
            return 0.0
        
        val, unit = match.groups()
        val = float(val)
        
        if unit == 'px':
            return val * 0.75  # Convert px to points
        elif unit == 'pt':
            return val
        elif unit == 'em' or unit == 'rem':
            return val * 12.0  # Assume 12pt base
        elif unit == '%':
            return (val / 100.0) * 12.0  # Assume 12pt base
        else:
            return val
    
    def html_to_pdf_reportlab(
        self, 
        html_content: str, 
        output_filename: Optional[str] = None,
        from_string: bool = True,
        stories: Optional[List[dict]] = None
    ) -> str:
        """
        Convert HTML to PDF using ReportLab
        
        Args:
            html_content: HTML string or file path
            output_filename: Custom filename for the PDF (optional)
            from_string: True if html_content is a string, False if it's a file path
            stories: Optional list of stories with page_number and text
            
        Returns:
            str: Path to the generated PDF file
            
        Raises:
            HTTPException: If PDF generation fails
        """
        try:
            # Generate unique filename if not provided
            if not output_filename:
                output_filename = f"generated_pdf_{uuid.uuid4().hex[:8]}.pdf"
            
            # Ensure filename has .pdf extension
            if not output_filename.endswith('.pdf'):
                output_filename += '.pdf'
            
            output_path = os.path.join(self.output_dir, output_filename)
            
            # Read HTML content
            if from_string:
                html_text = html_content
            else:
                with open(html_content, 'r', encoding='utf-8') as f:
                    html_text = f.read()
            
            # Parse HTML
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Parse CSS styles
            css_styles = self._parse_css(soup)
            
            # Check for story pages (your HTML structure)
            story_pages = soup.find_all('div', class_='story-page')
            image_containers = soup.find_all('div', class_='image-container')
            
            # Use story pages if available, otherwise fall back to image containers
            containers_to_process = story_pages if story_pages else image_containers
            
            # Compute maximum image width (for fallback, not used in dynamic sizing)
            max_image_width = A4[0] - (0.75 * inch + 0.75 * inch)
            
            # Create PDF document with dynamic page sizing
            # For story pages or image containers, we'll use custom page sizes
            if containers_to_process:
                # Generate PDF with dynamic page sizes for each image
                self._generate_dynamic_image_pdf(output_path, containers_to_process, max_image_width, css_styles, stories)
                logger.info(f"Dynamic PDF successfully generated: {output_path}")
                return output_path
            
            # For text-based PDFs, use standard A4
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            
            # Get base styles
            styles = getSampleStyleSheet()
            
            # Create custom styles with CSS support
            title_style = self._create_paragraph_style('CustomTitle', styles['Heading1'], {
                'font-size': '18pt',
                'color': '#2c3e50',
                'font-weight': 'bold'
            })
            
            heading_style = self._create_paragraph_style('CustomHeading', styles['Heading2'], {
                'font-size': '14pt',
                'color': '#2c3e50'
            })
            
            normal_style = self._create_paragraph_style('CustomNormal', styles['Normal'], {
                'font-size': '10pt'
            })
            
            # Build content
            story = []
            
            # Compute maximum image width based on page size and margins
            max_image_width = A4[0] - (0.75 * inch + 0.75 * inch)

            # Process HTML elements including images (for text-based PDFs)
            for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'img']):
                # Handle standalone images
                if element.name == 'img':
                    src = element.get('src', '').strip()
                    if src.startswith('data:image/') and ';base64,' in src:
                        try:
                            header, b64data = src.split(',', 1)
                            image_bytes = base64.b64decode(b64data)
                            image_stream = io.BytesIO(image_bytes)

                            # Determine intrinsic size to preserve aspect ratio
                            reader = ImageReader(image_stream)
                            intrinsic_width, intrinsic_height = reader.getSize()
                            if intrinsic_width == 0 or intrinsic_height == 0:
                                raise ValueError('Invalid image dimensions')

                            # Reset stream after size read
                            image_stream.seek(0)

                            # Apply width/height from attributes if provided
                            attr_width = element.get('width')
                            attr_height = element.get('height')

                            def parse_css_px(value: str) -> Optional[float]:
                                try:
                                    v = value.strip()
                                    if v.endswith('px'):
                                        v = v[:-2]
                                    return float(v)
                                except Exception:
                                    return None

                            target_width = None
                            target_height = None

                            # Prefer explicit attributes
                            if attr_width:
                                target_width = parse_css_px(str(attr_width))
                            if attr_height:
                                target_height = parse_css_px(str(attr_height))

                            # Try to parse from inline style if present
                            style_attr = element.get('style', '')
                            if style_attr:
                                # naive parsing for width/height
                                for rule in style_attr.split(';'):
                                    if not rule.strip():
                                        continue
                                    k, _, v = rule.partition(':')
                                    key = k.strip().lower()
                                    val = v.strip()
                                    if key == 'width' and target_width is None:
                                        pw = parse_css_px(val)
                                        if pw is not None:
                                            target_width = pw
                                    if key == 'height' and target_height is None:
                                        ph = parse_css_px(val)
                                        if ph is not None:
                                            target_height = ph

                            # Convert px to points (1 px ~ 0.75 pt at 96 DPI). We'll use 0.75.
                            PX_TO_PT = 0.75
                            if target_width is not None:
                                target_width *= PX_TO_PT
                            if target_height is not None:
                                target_height *= PX_TO_PT

                            # Maintain aspect ratio if only one dimension provided
                            aspect = intrinsic_height / float(intrinsic_width)
                            if target_width and not target_height:
                                target_height = target_width * aspect
                            elif target_height and not target_width:
                                target_width = target_height / aspect

                            # Constrain to maximum width
                            if target_width is None or target_width > max_image_width:
                                target_width = max_image_width
                                target_height = target_width * aspect

                            img_flowable = Image(image_stream, width=target_width, height=target_height)
                            # Center the image by setting hAlign
                            img_flowable.hAlign = 'CENTER'
                            story.append(img_flowable)
                            story.append(Spacer(1, 6))
                        except Exception as img_err:
                            logger.warning(f"Skipping image due to error: {img_err}")
                    # Non-base64 images are ignored for now
                    continue
                
                # Non-image elements: treat as text with CSS styling
                text = element.get_text().strip()
                if not text:
                    continue

                # Get computed styles for this element
                element_styles = self._get_element_styles(element, css_styles)
                
                # Create paragraph style based on element and CSS
                if element.name in ['h1']:
                    base_style = title_style
                elif element.name in ['h2', 'h3', 'h4', 'h5', 'h6']:
                    base_style = heading_style
                else:
                    base_style = normal_style
                
                # Apply CSS styles to create custom style
                custom_style = self._create_paragraph_style(
                    f'Custom_{element.name}_{id(element)}', 
                    base_style, 
                    element_styles
                )
                
                story.append(Paragraph(text, custom_style))
                story.append(Spacer(1, 6))
            
            # If no content was found, add a default message
            if not story:
                story.append(Paragraph("No content found in HTML", normal_style))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"PDF successfully generated: {output_path}")
            return output_path
            
        except Exception as e:
            error_msg = f"Error generating PDF: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
    
    def _generate_dynamic_image_pdf(self, output_path, image_containers, max_image_width, css_styles, stories=None):
        """
        Generate PDF with truly dynamic page sizes based on image dimensions
        """
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        import tempfile
        import os
        
        # Limit processing to avoid performance issues (max 20 containers)
        max_containers = min(len(image_containers), 20)
        logger.info(f"Generating dynamic PDF with {max_containers} image containers")
        
        # Create stories mapping by page number
        stories_by_page = {}
        if stories:
            for story in stories:
                page_num = story.page_number  # Access attribute directly, not dict
                text = story.text  # Access attribute directly, not dict
                stories_by_page[page_num] = text
                logger.info(f"Mapped page {page_num}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            logger.info(f"Created stories mapping for {len(stories_by_page)} pages")
        else:
            logger.info("No stories provided in request")
        
        # Create a new PDF with dynamic page sizes
        c = canvas.Canvas(output_path)
        
        for i in range(max_containers):
            container = image_containers[i]
            page_number = i + 1
            logger.info(f"Processing image container {page_number}/{max_containers}")
            
            try:
                # Start a new page (except for the first one)
                if i > 0:
                    c.showPage()
                
                # Get story text for this page
                story_text = stories_by_page.get(page_number, '')
                logger.info(f"Page {page_number} story_text: '{story_text[:50] if story_text else 'EMPTY'}{'...' if len(story_text) > 50 else ''}'")
                
                # Draw the content directly on the canvas with exact image dimensions
                self._draw_image_page(c, container, None, css_styles, story_text)
                
                logger.info(f"Added page {page_number} with exact image dimensions")
                    
            except Exception as e:
                logger.warning(f"Error processing container {page_number}: {e}")
                continue
        
        # Save the PDF
        c.save()
        logger.info(f"Dynamic PDF generated successfully: {output_path}")
    
    def _draw_image_page(self, canvas, container, page_size, css_styles, story_text=''):
        """
        Draw an image page directly on the canvas with the specified size
        """
        try:
            # Find the background image (could be in story-page or image-container)
            bg_img = container.find('img', class_='background-image')
            if not bg_img:
                return
            
            src = bg_img.get('src', '').strip()
            if not src.startswith('data:image/') or ';base64,' not in src:
                return
            
            # Decode base64 image
            header, b64data = src.split(',', 1)
            image_bytes = base64.b64decode(b64data)
            image_stream = io.BytesIO(image_bytes)
            
            # Get image dimensions
            reader = ImageReader(image_stream)
            intrinsic_width, intrinsic_height = reader.getSize()
            if intrinsic_width == 0 or intrinsic_height == 0:
                return
            
            # Reset stream
            image_stream.seek(0)
            
            # Calculate exact image dimensions in points (no margins, no extra space)
            PX_TO_PT = 0.75
            target_width = intrinsic_width * PX_TO_PT
            target_height = intrinsic_height * PX_TO_PT
            
            # Set the page size to exactly match the image dimensions
            canvas.setPageSize((target_width, target_height))
            
            logger.info(f"Drawing image with exact dimensions: {target_width:.1f}x{target_height:.1f} points")
            
            # Draw the image to fill the entire page with no margins
            # Reset stream to beginning
            image_stream.seek(0)
            canvas.drawImage(
                ImageReader(image_stream),
                0, 0,  # Position at bottom-left corner
                width=target_width,
                height=target_height,
                preserveAspectRatio=False  # Fill the entire page exactly
            )
            
            # Draw overlay content (text blocks, page numbers, etc.)
            self._draw_overlay_content(canvas, container, target_width, target_height, css_styles, story_text)
            
        except Exception as e:
            logger.warning(f"Error drawing image page: {e}")
    
    def _draw_overlay_content(self, canvas, container, width, height, css_styles, story_text=''):
        """
        Draw overlay text and metadata on the canvas
        """
        try:
            # Debug: Log what we're looking for
            logger.info(f"Looking for text elements in container: {container.name if hasattr(container, 'name') else 'Unknown'}")
            
            # Priority 1: Use story_text from API request if available
            text_to_draw = story_text.strip() if story_text else ''
            logger.info(f"Story text for drawing: '{text_to_draw[:50] if text_to_draw else 'EMPTY'}{'...' if len(text_to_draw) > 50 else ''}'")
            
            # Priority 2: Fall back to HTML structure if no story_text
            if not text_to_draw:
                text_block = container.find('div', class_='text-block')
                page_number = container.find('div', class_='page-number')
                
                logger.info(f"Found text_block: {text_block is not None}")
                logger.info(f"Found page_number: {page_number is not None}")
                
                if text_block:
                    text_to_draw = text_block.get_text().strip()
            
            # Draw text if we have any
            if text_to_draw:
                # Determine text type and apply appropriate styling
                text_lower = text_to_draw.lower()
                
                # Use ONLY Times-Bold font consistently across all pages
                font_name = "Times-Bold"  # Single consistent font for everything
                
                # Use consistent font size for all text (no size variations)
                font_size = 28  # Single consistent size for all text
                
                # Use consistent color for all text (black)
                canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color for all text
                
                # Set the consistent font
                canvas.setFont(font_name, font_size)
                
                # Split text into lines based on actual text width (much better than character count)
                words = text_to_draw.split()
                lines = []
                current_line = ""
                
                # Calculate maximum line width (90% of page width for better readability)
                max_line_width = width * 0.9
                
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    test_width = canvas.stringWidth(test_line, font_name, font_size)
                    
                    if test_width <= max_line_width:
                        current_line = test_line
                    else:
                        if current_line:  # Only append if current_line is not empty
                            lines.append(current_line)
                        current_line = word
                
                # Add the last line
                if current_line:
                    lines.append(current_line)
                
                # Position text block at bottom center area with dynamic spacing
                line_spacing = font_size * 1.4  # Better spacing based on font size
                
                # Allow more lines for longer text (up to 6 lines instead of 3)
                max_lines = min(6, len(lines))
                
                # Calculate starting Y position to accommodate all lines (start higher, go down)
                total_text_height = max_lines * line_spacing
                text_y = 60 + total_text_height  # Start higher to accommodate downward text
                
                # Draw each line centered, going DOWN from the starting position
                for i, line in enumerate(lines[:max_lines]):
                    # Center the text horizontally
                    text_width = canvas.stringWidth(line, font_name, font_size)
                    text_x = (width - text_width) / 2  # Center horizontally
                    canvas.drawString(text_x, text_y - (i * line_spacing), line)  # SUBTRACT to go DOWN
            
            # Draw page number (fallback to HTML if no story_text)
            page_number_elem = container.find('div', class_='page-number')
            if page_number_elem and not text_to_draw:
                page_num_text = page_number_elem.get_text().strip()
                if page_num_text:
                    # Set consistent font and color for page number
                    font_name = "Times-Bold"  # Same font as all other text
                    font_size = 28  # Same size as all other text
                    canvas.setFont(font_name, font_size)  # Consistent font across all pages
                    # Black color (same as all other text)
                    canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
                    
                    # Position page number at bottom right
                    text_width = canvas.stringWidth(page_num_text, font_name, font_size)
                    text_x = width - text_width - 20  # Right margin
                    text_y = 30  # Bottom area
                    
                    canvas.drawString(text_x, text_y, page_num_text)
            
            # Fallback: If no text found at all, draw a test text
            if not text_to_draw and not page_number_elem:
                logger.info("No text elements found, drawing test text")
                
                # Center the test text with title styling
                test_text1 = "TEST TEXT - This should be visible"
                test_text2 = f"Page size: {width:.1f}x{height:.1f}"
                
                # Consistent styling for test text
                font_name = "Times-Bold"  # Same font as all other text
                font_size = 28  # Same size as all other text
                canvas.setFont(font_name, font_size)  # Consistent font across all pages
                canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color (same as all other text)
                
                text_width1 = canvas.stringWidth(test_text1, font_name, font_size)
                text_width2 = canvas.stringWidth(test_text2, font_name, font_size)
                
                canvas.drawString((width - text_width1) / 2, 50, test_text1)
                canvas.drawString((width - text_width2) / 2, 80, test_text2)
            
            # Fallback: Handle old overlay-content structure
            overlay_content = container.find('div', class_='overlay-content')
            if overlay_content and not text_to_draw:
                # Draw main overlay text
                overlay_text_elem = overlay_content.find('div', class_='overlay-text')
                if overlay_text_elem:
                    text = overlay_text_elem.get_text().strip()
                    if text:
                        # Consistent font and color for overlay text
                        font_name = "Times-Bold"  # Same font as all other text
                        font_size = 28  # Same size as all other text
                        canvas.setFont(font_name, font_size)  # Consistent font across all pages
                        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color (same as all other text)
                        text_width = canvas.stringWidth(text, font_name, font_size)
                        
                        # Center the text at bottom
                        text_x = (width - text_width) / 2
                        text_y = 50
                        canvas.drawString(text_x, text_y, text)
                
                # Draw metadata items
                metadata_items = []
                for class_name in ['overlay-scene', 'overlay-visuals', 'overlay-model']:
                    elem = overlay_content.find('div', class_=class_name)
                    if elem:
                        metadata_items.append(elem.get_text().strip())
                
                if metadata_items:
                    # Use consistent font for metadata
                    font_name = "Times-Bold"  # Same font as all other text
                    font_size = 28  # Same size as all other text
                    canvas.setFont(font_name, font_size)  # Consistent font across all pages
                    canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color (same as all other text)
                    
                    for i, item in enumerate(metadata_items):
                        if item:
                            # Center each metadata item
                            item_width = canvas.stringWidth(item, font_name, font_size)
                            item_x = (width - item_width) / 2
                            canvas.drawString(item_x, 90 + (i * 25), item)
                        
        except Exception as e:
            logger.warning(f"Error drawing overlay content: {e}")
    
    def _process_storybook_container(self, container, max_width, css_styles):
        """
        Process a storybook image container with background image and overlay text
        
        Args:
            container: BeautifulSoup element representing the image container
            max_width: Maximum width for the container
            css_styles: Parsed CSS styles
            
        Returns:
            ReportLab flowable representing the storybook page
        """
        from reportlab.platypus import Frame, PageTemplate, BaseDocTemplate
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        try:
            # Find the background image
            bg_img = container.find('img', class_='background-image')
            if not bg_img:
                return Paragraph("No background image found", getSampleStyleSheet()['Normal'])
            
            src = bg_img.get('src', '').strip()
            if not src.startswith('data:image/') or ';base64,' not in src:
                return Paragraph("Invalid image format", getSampleStyleSheet()['Normal'])
            
            # Decode base64 image (optimized)
            try:
                header, b64data = src.split(',', 1)
                image_bytes = base64.b64decode(b64data)
                image_stream = io.BytesIO(image_bytes)
            except Exception as e:
                logger.warning(f"Failed to decode image: {e}")
                return Paragraph("Invalid image data", getSampleStyleSheet()['Normal'])
            
            # Get image dimensions
            reader = ImageReader(image_stream)
            intrinsic_width, intrinsic_height = reader.getSize()
            if intrinsic_width == 0 or intrinsic_height == 0:
                raise ValueError('Invalid image dimensions')
            
            # Reset stream
            image_stream.seek(0)
            
            # Use actual image dimensions for PDF page size
            # Convert pixels to points (1 px = 0.75 pt at 96 DPI)
            PX_TO_PT = 0.75
            
            # Calculate target dimensions based on actual image size
            target_width = intrinsic_width * PX_TO_PT
            target_height = intrinsic_height * PX_TO_PT
            
            # Scale down if image is too large (max width/height limits)
            max_page_width = 8.5 * 72  # 8.5 inches in points
            max_page_height = 11 * 72   # 11 inches in points
            
            if target_width > max_page_width or target_height > max_page_height:
                # Scale down proportionally
                width_scale = max_page_width / target_width
                height_scale = max_page_height / target_height
                scale = min(width_scale, height_scale)
                
                target_width = target_width * scale
                target_height = target_height * scale
            
            # Create the background image
            bg_image = Image(image_stream, width=target_width, height=target_height)
            bg_image.hAlign = 'CENTER'
            
            # Store page size for document creation
            page_size = (target_width, target_height)
            logger.info(f"Image dimensions: {intrinsic_width}x{intrinsic_height} -> PDF size: {target_width:.1f}x{target_height:.1f} points")
            logger.info(f"Page size tuple: {page_size}")
            
            # Extract overlay content with CSS styling
            overlay_content = container.find('div', class_='overlay-content')
            overlay_text = ""
            overlay_text_styles = {}
            metadata_items = []
            metadata_styles = []
            
            if overlay_content:
                # Get main text with styles
                text_elem = overlay_content.find('div', class_='overlay-text')
                if text_elem:
                    overlay_text = text_elem.get_text().strip()
                    overlay_text_styles = self._get_element_styles(text_elem, css_styles)
                
                # Get metadata with styles
                metadata = overlay_content.find('div', class_='overlay-metadata')
                if metadata:
                    scene = metadata.find('div', class_='overlay-scene')
                    visuals = metadata.find('div', class_='overlay-visuals')
                    model = metadata.find('div', class_='overlay-model')
                    
                    if scene:
                        scene_text = scene.get_text().strip()
                        scene_styles = self._get_element_styles(scene, css_styles)
                        metadata_items.append(scene_text)
                        metadata_styles.append(scene_styles)
                    if visuals:
                        visuals_text = visuals.get_text().strip()
                        visuals_styles = self._get_element_styles(visuals, css_styles)
                        metadata_items.append(visuals_text)
                        metadata_styles.append(visuals_styles)
                    if model:
                        model_text = model.get_text().strip()
                        model_styles = self._get_element_styles(model, css_styles)
                        metadata_items.append(model_text)
                        metadata_styles.append(model_styles)
            
            # Create a custom flowable that combines image and text
            from reportlab.platypus.flowables import Flowable
            
            class StorybookPage(Flowable):
                def __init__(self, bg_image, overlay_text, overlay_text_styles, metadata_items, metadata_styles, width, height, pdf_service):
                    Flowable.__init__(self)
                    self.bg_image = bg_image
                    self.overlay_text = overlay_text
                    self.overlay_text_styles = overlay_text_styles
                    self.metadata_items = metadata_items
                    self.metadata_styles = metadata_styles
                    self.width = width
                    self.height = height
                    self.pdf_service = pdf_service
                
                def getPageSize(self):
                    """Return the page size for this flowable"""
                    return (self.width, self.height)
                
                def draw(self):
                    # Set the canvas size to match our image dimensions
                    self.canv.setPageSize((self.width, self.height))
                    
                    # Draw background image
                    self.bg_image.drawOn(self.canv, 0, 0)
                    
                    # Draw dark overlay effect
                    self.canv.setFillColor(colors.black)
                    self.canv.setFillAlpha(0.3)
                    self.canv.rect(0, 0, self.width, self.height, fill=1)
                    
                    # Draw main text overlay with CSS styling
                    if self.overlay_text:
                        # Apply CSS styles to text
                        font_size = 16
                        font_color = colors.white
                        font_weight = "Helvetica-Bold"
                        
                        if 'font-size' in self.overlay_text_styles:
                            font_size = self.pdf_service._parse_font_size(self.overlay_text_styles['font-size'])
                        if 'color' in self.overlay_text_styles:
                            font_color = self.pdf_service._parse_color(self.overlay_text_styles['color'])
                        if 'font-weight' in self.overlay_text_styles:
                            weight = self.overlay_text_styles['font-weight'].lower()
                            if weight in ['bold', 'bolder']:
                                font_weight = "Helvetica-Bold"
                            else:
                                font_weight = "Helvetica"
                        
                        self.canv.setFillColor(font_color)
                        self.canv.setFont(font_weight, font_size)
                        
                        # Create a text box with background
                        text_width = self.width * 0.8
                        text_height = 60
                        text_x = (self.width - text_width) / 2
                        text_y = self.height * 0.6
                        
                        # Draw text background
                        self.canv.setFillColor(colors.black)
                        self.canv.setFillAlpha(0.8)
                        self.canv.roundRect(text_x, text_y, text_width, text_height, 10, fill=1)
                        
                        # Draw text (centered)
                        self.canv.setFillColor(font_color)
                        text_width_actual = self.canv.stringWidth(self.overlay_text, font_weight, font_size)
                        text_x_centered = text_x + (text_width - text_width_actual) / 2
                        text_y_centered = text_y + (text_height - font_size) / 2
                        self.canv.drawString(text_x_centered, text_y_centered, self.overlay_text)
                    
                    # Draw metadata with CSS styling
                    if self.metadata_items:
                        y_offset = self.height * 0.3
                        for i, (item, item_styles) in enumerate(zip(self.metadata_items, self.metadata_styles)):
                            # Apply CSS styles to metadata
                            font_size = 10
                            font_color = colors.white
                            font_weight = "Helvetica"
                            
                            if 'font-size' in item_styles:
                                font_size = self.pdf_service._parse_font_size(item_styles['font-size'])
                            if 'color' in item_styles:
                                font_color = self.pdf_service._parse_color(item_styles['color'])
                            if 'font-weight' in item_styles:
                                weight = item_styles['font-weight'].lower()
                                if weight in ['bold', 'bolder']:
                                    font_weight = "Helvetica-Bold"
                                else:
                                    font_weight = "Helvetica"
                            
                            self.canv.setFillColor(font_color)
                            self.canv.setFont(font_weight, font_size)
                            
                            # Draw metadata background
                            meta_width = self.width * 0.7
                            meta_height = 20
                            meta_x = (self.width - meta_width) / 2
                            meta_y = y_offset - (i * 25)
                            
                            self.canv.setFillColor(colors.black)
                            self.canv.setFillAlpha(0.7)
                            self.canv.roundRect(meta_x, meta_y, meta_width, meta_height, 5, fill=1)
                            
                            # Draw metadata text (centered)
                            self.canv.setFillColor(font_color)
                            meta_text_width_actual = self.canv.stringWidth(item, font_weight, font_size)
                            meta_x_centered = meta_x + (meta_width - meta_text_width_actual) / 2
                            meta_y_centered = meta_y + (meta_height - font_size) / 2
                            self.canv.drawString(meta_x_centered, meta_y_centered, item)
            
            flowable = StorybookPage(bg_image, overlay_text, overlay_text_styles, metadata_items, metadata_styles, target_width, target_height, self)
            return flowable, page_size
            
        except Exception as e:
            logger.warning(f"Error processing storybook container: {e}")
            error_para = Paragraph(f"Error processing storybook page: {str(e)}", getSampleStyleSheet()['Normal'])
            return error_para, A4  # Return error with default page size
    
    def get_pdf_file_path(self, filename: str) -> str:
        """
        Get full path for a PDF file
        
        Args:
            filename: PDF filename
            
        Returns:
            str: Full path to the PDF file
        """
        return os.path.join(self.output_dir, filename)
    
    def file_exists(self, filename: str) -> bool:
        """
        Check if a PDF file exists
        
        Args:
            filename: PDF filename
            
        Returns:
            bool: True if file exists, False otherwise
        """
        file_path = self.get_pdf_file_path(filename)
        return os.path.exists(file_path)

    async def generate_storybook_pdf(self, metadata, pages, filename=None):
        """
        Generate a comprehensive children's storybook PDF with metadata and story pages
        
        Args:
            metadata: BookMetadata object with title, author, theme, etc.
            pages: List of StorybookPage objects with story_text and illustration_prompt
            filename: Optional custom filename
            
        Returns:
            dict: Result with filename and file_path
        """
        try:
            # Generate filename if not provided
            if not filename:
                import re
                filename = re.sub(r'[^\w\-_.]', '_', metadata.title.lower())
                filename = f"{filename}_storybook"
            
            # Ensure filename ends with .pdf
            if not filename.endswith('.pdf'):
                filename += '.pdf'
                
            # Create output path
            output_path = self.get_pdf_file_path(filename)
            
            logger.info(f"Generating storybook PDF: {filename}")
            logger.info(f"Title: {metadata.title}")
            logger.info(f"Author: {metadata.author}")
            logger.info(f"Pages: {len(pages)}")
            
            # Generate the storybook PDF using ReportLab
            self._generate_storybook_pdf_reportlab(output_path, metadata, pages)
            
            logger.info(f"Storybook PDF generated successfully: {output_path}")
            return {
                "filename": filename,
                "file_path": output_path
            }
            
        except Exception as e:
            logger.error(f"Error generating storybook PDF: {str(e)}")
            raise
    
    async def generate_simple_storybook_pdf(self, page_number: int, text: str, image_url: str, filename: Optional[str] = None):
        """
        Generate a storybook PDF from simplified request with URL image
        
        Args:
            page_number: Page number for this story
            text: Story text content
            image_url: URL to the illustration image
            filename: Optional custom filename
            
        Returns:
            dict: Result with filename and file_path
        """
        try:
            from app.models.pdf_models import BookMetadata, StorybookPage
            
            # Generate filename if not provided
            if not filename:
                # Extract title from text (first few words)
                title_words = text.split()[:4]  # First 4 words
                title = " ".join(title_words)
                filename = re.sub(r'[^\w\-_.]', '_', title.lower())
                filename = f"{filename}_storybook"
            
            # Ensure filename ends with .pdf
            if not filename.endswith('.pdf'):
                filename += '.pdf'
            
            # Create output path
            output_path = self.get_pdf_file_path(filename)
            
            # Download the image from URL
            image_data = self._download_image_from_url(image_url)
            
            # Convert image data to base64 for processing (if successfully downloaded)
            image_base64 = None
            if image_data:
                import base64
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                # Add data URL prefix (assume JPEG for now, could be enhanced to detect format)
                image_base64 = f"data:image/jpeg;base64,{image_base64}"
                logger.info(f"Successfully downloaded and converted image: {len(image_data)} bytes")
            else:
                logger.warning(f"Could not download image from URL: {image_url}")
            
            # Create metadata from text
            # Extract title from text (first part before any punctuation or keywords)
            title_parts = re.split(r'[\.!?]|\sand\s', text)
            title = title_parts[0].strip() if title_parts else text[:50]
            
            metadata = BookMetadata(
                title=title,
                author="Generated Author",
                age_range="All Ages",
                theme="Adventure and Learning",
                moral_lesson="Every story teaches us something wonderful."
            )
            
            # Create storybook page
            page = StorybookPage(
                page_number=page_number,
                story_text=text,
                illustration_prompt=f"Create a children's book illustration for: {text[:100]}...",
                image_data=image_base64  # Use downloaded image
            )
            
            # Log generation details
            logger.info(f"Generating simple storybook PDF: {filename}")
            logger.info(f"Title: {metadata.title}")
            logger.info(f"Text: {text[:100]}...")
            logger.info(f"Image URL: {image_url}")
            logger.info(f"Image downloaded: {'Yes' if image_data else 'No'}")
            
            # Generate PDF with single page
            self._generate_storybook_pdf_reportlab(output_path, metadata, [page])
            
            logger.info(f"Simple storybook PDF generated successfully: {output_path}")
            
            return {
                "filename": filename,
                "file_path": output_path
            }
            
        except Exception as e:
            logger.error(f"Error generating simple storybook PDF: {str(e)}")
            raise
    
    async def generate_kdp_storybook_pdf(self, pages: List, filename: Optional[str] = None, text_overlay_opacity: float = 0.7, page_width: float = 612.0, page_height: float = 792.0, title_color: Optional[str] = None, title_font_size: Optional[int] = None, text_font_size: Optional[int] = None, text_color: Optional[str] = None):
        """
        Generate a KDP-ready storybook PDF from page array with different page types
        
        Args:
            pages: List of KDPStorybookPage objects with page_type, text, and image_url
            filename: Optional custom filename
            
        Returns:
            dict: Result with filename and file_path
        """
        try:
            # Generate filename if not provided
            if not filename:
                # Extract title from first cover page
                cover_page = next((p for p in pages if p.page_type == "cover"), None)
                if cover_page:
                    title_words = cover_page.text.split()[:4]  # First 4 words
                    title = " ".join(title_words)
                    filename = re.sub(r'[^\w\-_.]', '_', title.lower())
                    filename = f"{filename}_kdp_storybook"
                else:
                    filename = "kdp_storybook"
            
            # Ensure filename ends with .pdf
            if not filename.endswith('.pdf'):
                filename += '.pdf'
            
            # Create output path
            output_path = self.get_pdf_file_path(filename)
            
            # Download images and create overlays for all pages
            for page in pages:
                image_data = self._download_image_from_url(page.image_url)
                if image_data:
                    # For cover pages, use original image without cloud overlay
                    if page.page_type == "cover":
                        # Store original image for cover pages (no cloud overlay)
                        import base64
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        page.image_data = f"data:image/jpeg;base64,{image_base64}"
                        logger.info(f"Downloaded cover image for page {page.page_number}: {len(image_data)} bytes")
                    else:
                        # Create fluffy cloud text overlay for story and end pages
                        # Use API parameters for font size and color
                        page_font_size = getattr(page, 'text_font_size', None) or (36 if page.page_type == "story" else 34)
                        page_text_color = getattr(page, 'text_color', None) or "#000000"
                        
                        if page.page_type == "story":
                            composite_image = self._create_fluffy_cloud_overlay(
                                image_data, page.text, font_size=page_font_size,
                                opacity=text_overlay_opacity, position="top", text_color=page_text_color
                            )
                        else:  # end page
                            composite_image = self._create_fluffy_cloud_overlay(
                                image_data, page.text, font_size=page_font_size,
                                opacity=text_overlay_opacity, position="center", text_color=page_text_color
                            )
                        
                        # Convert composite image to base64 for ReportLab
                        import base64
                        image_base64 = base64.b64encode(composite_image).decode('utf-8')
                        page.image_data = f"data:image/jpeg;base64,{image_base64}"
                        logger.info(f"Created fluffy cloud overlay for page {page.page_number}: {len(composite_image)} bytes")
                else:
                    page.image_data = None
                    logger.warning(f"Could not download image for page {page.page_number}: {page.image_url}")
            
            # Log generation details
            logger.info(f"Generating KDP storybook PDF: {filename}")
            logger.info(f"Total pages: {len(pages)}")
            
            # Generate PDF with KDP layout
            self._generate_kdp_storybook_pdf_reportlab(output_path, pages, text_overlay_opacity, page_width, page_height, title_color, title_font_size, text_font_size, text_color)
            
            logger.info(f"KDP storybook PDF generated successfully: {output_path}")
            
            return {
                "filename": filename,
                "file_path": output_path
            }
            
        except Exception as e:
            logger.error(f"Error generating KDP storybook PDF: {str(e)}")
            raise
    
    def _generate_kdp_storybook_pdf_reportlab(self, output_path, pages, text_overlay_opacity=0.7, page_width=612.0, page_height=792.0, title_color=None, title_font_size=None, text_font_size=None, text_color=None):
        """
        Generate KDP storybook PDF using ReportLab with different page types
        
        Args:
            output_path: Output file path
            pages: List of KDPStorybookPage objects
            text_overlay_opacity: Opacity for text overlay backgrounds (0.0-1.0)
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            from io import BytesIO
            import base64
            
            # Create PDF with custom page dimensions
            page_size = (page_width, page_height)
            c = canvas.Canvas(output_path, pagesize=page_size)
            
            logger.info(f"Creating KDP PDF with custom page size: {page_size} ({page_width/72:.1f}\" x {page_height/72:.1f}\")")
            logger.info(f"Text overlay opacity: {text_overlay_opacity}")
            logger.info("Using built-in Times-Bold font consistently across all pages")
            
            for page in pages:
                logger.info(f"Drawing {page.page_type} page {page.page_number}: {page.text[:50]}...")
                
                if page.page_type == "cover":
                    # Apply global title color to cover page if provided
                    if title_color and (not hasattr(page, 'title_color') or not page.title_color):
                        page.title_color = title_color
                    # Apply global title font size to cover page if provided
                    if title_font_size and (not hasattr(page, 'title_font_size') or not page.title_font_size):
                        page.title_font_size = title_font_size
                    self._draw_kdp_cover_page(c, page, page_width, page_height, text_overlay_opacity)
                elif page.page_type == "story":
                    # Apply global text styling to story page if provided
                    if text_font_size and (not hasattr(page, 'text_font_size') or not page.text_font_size):
                        page.text_font_size = text_font_size
                    if text_color and (not hasattr(page, 'text_color') or not page.text_color):
                        page.text_color = text_color
                    self._draw_kdp_story_page(c, page, page_width, page_height, text_overlay_opacity)
                elif page.page_type == "end":
                    # Apply global text styling to end page if provided
                    if text_font_size and (not hasattr(page, 'text_font_size') or not page.text_font_size):
                        page.text_font_size = text_font_size
                    if text_color and (not hasattr(page, 'text_color') or not page.text_color):
                        page.text_color = text_color
                    self._draw_kdp_end_page(c, page, page_width, page_height, text_overlay_opacity)
                
                # Add new page if not the last page
                if page.page_number < len(pages):
                    c.showPage()
                
                logger.info(f"Successfully drew {page.page_type} page {page.page_number}")
            
            # Save the PDF
            c.save()
            logger.info(f"KDP storybook PDF saved: {output_path}")
            
        except Exception as e:
            logger.error(f"Error in KDP PDF generation: {str(e)}")
            raise
    
    def _draw_kdp_cover_page(self, canvas, page, width, height, text_overlay_opacity=0.7):
        """Draw an attractive KDP cover page with professional design elements"""
        
        # Define margin for fallback placeholder
        margin = 18  # 0.25 inch margin (18 points)
        
        # Draw full-page cover image WITHOUT margins for bleed-ready design
        if hasattr(page, 'image_data') and page.image_data:
            # For cover pages, use COVER MODE to fill entire page (no white space)
            self._draw_kdp_image(canvas, 0, 0, width, height, page.image_data, cover_mode=True)
            
            # Add professional title overlay on top of the image
            self._draw_cover_title_overlay(canvas, page, width, height)
        else:
            # Create a beautiful children's book cover background
            # Sky gradient background
            canvas.setFillColorRGB(0.6, 0.8, 1.0)  # Light sky blue
            canvas.rect(margin, margin, width - 2*margin, height - 2*margin, fill=1, stroke=0)
            
            # Add grass/ground at bottom (like the reference image)
            canvas.setFillColorRGB(0.3, 0.7, 0.3)  # Forest green
            canvas.rect(margin, margin, width - 2*margin, (height - 2*margin) * 0.4, fill=1, stroke=0)
            
            # Add decorative trees (like the reference image)
            canvas.setFillColorRGB(0.4, 0.2, 0.1)  # Brown tree trunks
            # Left tree
            canvas.rect(width * 0.15, height * 0.2, 15, height * 0.3, fill=1, stroke=0)
            canvas.setFillColorRGB(0.2, 0.6, 0.2)  # Dark green foliage
            canvas.circle(width * 0.22, height * 0.5, 40, fill=1, stroke=0)
            
            # Right tree
            canvas.setFillColorRGB(0.4, 0.2, 0.1)  # Brown tree trunk
            canvas.rect(width * 0.75, height * 0.25, 12, height * 0.25, fill=1, stroke=0)
            canvas.setFillColorRGB(0.2, 0.6, 0.2)  # Dark green foliage
            canvas.circle(width * 0.81, height * 0.45, 35, fill=1, stroke=0)
            
            # Add fluffy white clouds in sky
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White clouds
            # Cloud 1 - top left
            canvas.circle(width * 0.2, height * 0.8, 30, fill=1, stroke=0)
            canvas.circle(width * 0.25, height * 0.82, 25, fill=1, stroke=0)
            canvas.circle(width * 0.15, height * 0.78, 20, fill=1, stroke=0)
            
            # Cloud 2 - top right
            canvas.circle(width * 0.8, height * 0.75, 35, fill=1, stroke=0)
            canvas.circle(width * 0.85, height * 0.77, 30, fill=1, stroke=0)
            canvas.circle(width * 0.75, height * 0.73, 25, fill=1, stroke=0)
            
            # Add a bright sun
            canvas.setFillColorRGB(1.0, 0.9, 0.0)  # Yellow sun
            canvas.circle(width * 0.9, height * 0.9, 25, fill=1, stroke=0)
            
            # Add decorative fence (like the reference image)
            canvas.setFillColorRGB(0.6, 0.4, 0.2)  # Wooden fence color
            for i in range(5):
                fence_x = width * 0.1 + (i * 20)
                canvas.rect(fence_x, height * 0.15, 3, height * 0.15, fill=1, stroke=0)
            
            # Add some decorative flowers/plants
            canvas.setFillColorRGB(1.0, 0.8, 0.8)  # Pink flowers
            canvas.circle(width * 0.3, height * 0.2, 8, fill=1, stroke=0)
            canvas.circle(width * 0.6, height * 0.18, 6, fill=1, stroke=0)
            canvas.circle(width * 0.4, height * 0.15, 7, fill=1, stroke=0)
            
            # Create an attractive title area with decorative background
            title_area_x = width * 0.1
            title_area_y = height * 0.6
            title_area_width = width * 0.8
            title_area_height = 120
            
            # Draw decorative title background (cloud-like shape)
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White background
            # Multiple overlapping circles for fluffy cloud effect
            for i in range(8):
                offset_x = i * (title_area_width / 8)
                canvas.circle(title_area_x + offset_x, title_area_y, 30, fill=1, stroke=0)
                canvas.circle(title_area_x + offset_x + 15, title_area_y + 15, 25, fill=1, stroke=0)
            
            # Add title text with shadow effect (like the reference)
            canvas.setFont("Times-Bold", 32)
            canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black shadow
            title_text = page.text
            title_width = canvas.stringWidth(title_text, "Times-Bold", 32)
            title_x = title_area_x + (title_area_width - title_width) / 2
            title_y = title_area_y + 40
            
            # Draw shadow
            canvas.drawString(title_x + 2, title_y - 2, title_text)
            
            # Draw main title text
            canvas.setFillColorRGB(0.1, 0.5, 0.1)  # Dark green (like the reference)
            canvas.drawString(title_x, title_y, title_text)
            
            # Add author name in decorative box (like the reference)
            author_x = width * 0.7
            author_y = height * 0.15
            author_width = 100
            author_height = 40
            
            # Draw author background box
            canvas.setFillColorRGB(0.95, 0.95, 0.9)  # Light beige
            canvas.roundRect(author_x, author_y, author_width, author_height, 10, fill=1, stroke=1)
            
            # Add author text
            canvas.setFont("Times-Bold", 14)
            canvas.setFillColorRGB(0.1, 0.5, 0.1)  # Dark green
            author_text = "Author Name"
            author_text_width = canvas.stringWidth(author_text, "Times-Bold", 14)
            author_text_x = author_x + (author_width - author_text_width) / 2
            canvas.drawString(author_text_x, author_y + 15, author_text)
            
            # Add subtitle/tagline at bottom (like the reference)
            canvas.setFont("Times-Bold", 12)
            canvas.setFillColorRGB(0.3, 0.3, 0.3)  # Dark gray
            tagline = "A Magical Adventure Story"
            tagline_width = canvas.stringWidth(tagline, "Times-Bold", 12)
            tagline_x = (width - tagline_width) / 2
            canvas.drawString(tagline_x, margin + 40, tagline)
    
    def _draw_cover_title_overlay(self, canvas, page, width, height):
        """Draw professional cover title styled like the reference image.

        Style: single warm golden title (or dark navy on bright backgrounds),
        with subtle outline and soft shadow. Auto color chosen from background
        brightness to ensure contrast. Up to 3 wrapped lines, centered.
        """

        # Title text
        title_text = page.text

        # Choose base font size (use API parameter if provided, otherwise auto-calculate)
        if hasattr(page, 'title_font_size') and page.title_font_size:
            title_font_size = page.title_font_size
        else:
            # Auto-calculate based on title length
            title_font_size = 150 if len(title_text) < 15 else 130 if len(title_text) < 25 else 110

        # Determine background brightness in the top area where title sits
        # Default to medium value if image not available
        avg_luma = 0.5
        try:
            from PIL import Image
            import io
            if hasattr(page, 'image_data') and page.image_data:
                img = Image.open(io.BytesIO(page.image_data)).convert('RGB')
                # Sample the top 35% region
                top_h = max(1, int(img.height * 0.35))
                crop = img.crop((0, 0, img.width, top_h)).resize((64, 64))
                pixels = list(crop.getdata())
                # Luminance per ITU-R BT.709
                lum = [(0.2126*r + 0.7152*g + 0.0722*b)/255.0 for (r,g,b) in pixels]
                avg_luma = sum(lum) / len(lum)
        except Exception:
            pass

        # If API provides explicit title color, parse and use it; otherwise choose based on brightness
        def _hex_to_rgb01(hex_str: str):
            hex_str = hex_str.strip().lstrip('#')
            if len(hex_str) == 6:
                r = int(hex_str[0:2], 16) / 255.0
                g = int(hex_str[2:4], 16) / 255.0
                b = int(hex_str[4:6], 16) / 255.0
                return (r, g, b)
            return None

        provided_color = getattr(page, 'title_color', None)
        logger.info(f"Cover page title color: {provided_color}")
        parsed = _hex_to_rgb01(provided_color) if provided_color else None

        if parsed is not None:
            title_rgb = parsed
            # Choose outline automatically for contrast
            # compute luma
            luma = 0.2126*title_rgb[0] + 0.7152*title_rgb[1] + 0.0722*title_rgb[2]
            outline_rgb = (0.05, 0.05, 0.05) if luma > 0.6 else (1.0, 1.0, 1.0)
            shadow_rgb = (0.0, 0.0, 0.0)
        else:
            # Pick palette based on brightness
            if avg_luma < 0.55:
                # Dark background → warm golden title with darker outline
                title_rgb = (0.96, 0.80, 0.35)   # gold/yellow
                outline_rgb = (0.48, 0.32, 0.05) # deep ochre
                shadow_rgb = (0.0, 0.0, 0.0)
            else:
                # Bright background → dark navy title with light outline
                title_rgb = (0.16, 0.23, 0.35)   # dark navy
                outline_rgb = (1.0, 1.0, 1.0)    # white outline
                shadow_rgb = (0.0, 0.0, 0.0)

        # Wrap to up to 3 lines and center
        max_width = width * 0.86
        title_lines = self._wrap_text_to_lines(canvas, title_text, "Times-Bold", title_font_size, max_width)
        title_lines = title_lines[:3]

        # Vertical placement (center of page)
        line_height = title_font_size + 20
        total_height = len(title_lines) * line_height
        start_y = (height + total_height) / 2  # Center vertically

        # Draw each line with shadow and outline, then fill
        for line_idx, line in enumerate(title_lines):
            canvas.setFont("Times-Bold", title_font_size)
            line_width = canvas.stringWidth(line, "Times-Bold", title_font_size)
            line_x = (width - line_width) / 2
            current_y = start_y - (line_idx * line_height)

            # Soft shadow
            canvas.setFillColorRGB(*shadow_rgb)
            canvas.drawString(line_x + 3, current_y - 3, line)

            # Outline (draw the line multiple times slightly offset)
            canvas.setFillColorRGB(*outline_rgb)
            for dx in (-1.8, 1.8, 0, 0):
                for dy in (0, 0, -1.8, 1.8):
                    canvas.drawString(line_x + dx, current_y + dy, line)

            # Fill
            canvas.setFillColorRGB(*title_rgb)
            canvas.drawString(line_x, current_y, line)
    
    def _draw_kdp_story_page(self, canvas, page, width, height, text_overlay_opacity=0.7):
        """Draw a KDP story page with fluffy cloud text overlay (text overlay handled by Pillow)"""
        margin = 18  # 0.25 inch margin (18 points)
        
        # Draw full-page illustration with fluffy cloud text overlay
        if hasattr(page, 'image_data') and page.image_data:
            # Image already has fluffy cloud text overlay from Pillow processing
            self._draw_kdp_image(canvas, margin, margin, 
                                width - 2*margin, height - 2*margin, page.image_data)
        else:
            # Create a beautiful children's book style placeholder
            # Sky gradient background
            canvas.setFillColorRGB(0.6, 0.8, 1.0)  # Sky blue
            canvas.rect(margin, margin, width - 2*margin, height - 2*margin, fill=1, stroke=0)
            
            # Add grass/ground at bottom
            canvas.setFillColorRGB(0.4, 0.8, 0.3)  # Green grass
            canvas.rect(margin, margin, width - 2*margin, (height - 2*margin) * 0.3, fill=1, stroke=0)
            
            # Add fluffy white clouds
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White clouds
            # Cloud 1 - top left
            canvas.circle(width * 0.2, height * 0.8, 25, fill=1, stroke=0)
            canvas.circle(width * 0.25, height * 0.82, 20, fill=1, stroke=0)
            canvas.circle(width * 0.15, height * 0.78, 18, fill=1, stroke=0)
            
            # Cloud 2 - top right
            canvas.circle(width * 0.8, height * 0.75, 30, fill=1, stroke=0)
            canvas.circle(width * 0.85, height * 0.77, 25, fill=1, stroke=0)
            canvas.circle(width * 0.75, height * 0.73, 22, fill=1, stroke=0)
            
            # Add a simple sun
            canvas.setFillColorRGB(1.0, 0.9, 0.0)  # Yellow sun
            canvas.circle(width * 0.9, height * 0.9, 20, fill=1, stroke=0)
            
            # Add the story text with fluffy cloud background (manually positioned at top)
            cloud_x = width * 0.1
            cloud_y = height * 0.85
            cloud_width = width * 0.8
            cloud_height = 80
            
            # Draw fluffy cloud background for text
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White cloud
            # Multiple overlapping circles for fluffy effect
            for i in range(6):
                offset_x = i * (cloud_width / 6)
                canvas.circle(cloud_x + offset_x, cloud_y, 25, fill=1, stroke=0)
                canvas.circle(cloud_x + offset_x + 15, cloud_y + 15, 20, fill=1, stroke=0)
            
            # Add story text inside the cloud
            canvas.setFont("Times-Bold", 18)
            canvas.setFillColorRGB(0.1, 0.1, 0.5)  # Dark blue text
            
            # Wrap text to fit in cloud
            text_lines = self._wrap_text_to_lines(canvas, page.text, "Times-Bold", 18, cloud_width * 0.8)
            
            # Draw text lines
            line_height = 22
            start_y = cloud_y + 10
            for i, line in enumerate(text_lines[:3]):  # Max 3 lines
                line_width = canvas.stringWidth(line, "Times-Bold", 18)
                line_x = cloud_x + (cloud_width - line_width) / 2
                canvas.drawString(line_x, start_y - (i * line_height), line)
            
            # Add instruction text at bottom
            canvas.setFont("Times-Bold", 14)
            canvas.setFillColorRGB(0.8, 0.2, 0.2)  # Red text
            instruction = "Image not accessible. Please ensure Google Drive files are shared publicly."
            inst_width = canvas.stringWidth(instruction, "Times-Bold", 14)
            inst_x = (width - inst_width) / 2
            canvas.drawString(inst_x, margin + 30, instruction)
        
        # Add page number in bottom right corner
        canvas.setFont("Times-Bold", 18)
        canvas.setFillColorRGB(0.3, 0.3, 0.3)
        page_text = str(page.page_number)
        text_width = canvas.stringWidth(page_text, "Times-Bold", 18)
        
        # Draw page number with small background circle
        page_x = width - margin - 40
        page_y = margin + 20
        canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White background
        canvas.circle(page_x, page_y, 15, fill=1, stroke=1)
        canvas.setFillColorRGB(0.3, 0.3, 0.3)
        canvas.drawString(page_x - text_width/2, page_y - 6, page_text)
    
    def _draw_kdp_end_page(self, canvas, page, width, height, text_overlay_opacity=0.7):
        """Draw a KDP end page with fluffy cloud text overlay - FULL BLEED (no white space)"""
        
        # Define margin for fallback placeholder
        margin = 18  # 0.25 inch margin (18 points)
        
        # Draw full-page background image edge-to-edge (no margins)
        if hasattr(page, 'image_data') and page.image_data:
            # Use COVER MODE for full-bleed end page (no white space)
            self._draw_kdp_image(canvas, 0, 0, width, height, page.image_data, cover_mode=True)
        else:
            # Create a warm, celebratory background
            canvas.setFillColorRGB(1.0, 0.95, 0.8)  # Warm cream background
            canvas.rect(margin, margin, width - 2*margin, height - 2*margin, fill=1, stroke=0)
            
            # Add decorative fluffy cloud elements
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White clouds
            canvas.circle(width*0.2, height*0.8, 30, fill=1, stroke=0)
            canvas.circle(width*0.8, height*0.7, 25, fill=1, stroke=0)
            canvas.circle(width*0.3, height*0.3, 35, fill=1, stroke=0)
            canvas.circle(width*0.7, height*0.2, 28, fill=1, stroke=0)
            
            # Add fallback text if no image
            canvas.setFont("Times-Bold", 20)
            canvas.setFillColorRGB(0.1, 0.1, 0.1)
            text_width = canvas.stringWidth("End Image Not Available", "Times-Bold", 20)
            text_x = (width - text_width) / 2
            text_y = height / 2
            canvas.drawString(text_x, text_y, "End Image Not Available")
        
        # Add "Powered by @freemindAI" branding at bottom center
        self._draw_freemind_branding(canvas, width, height)
    
    def _draw_freemind_branding(self, canvas, width, height):
        """Draw 'Powered by @freemindAI' branding at bottom center of end page"""
        
        # Set font and color for branding (increased font size)
        canvas.setFont("Times-Bold", 18)
        canvas.setFillColorRGB(0.3, 0.3, 0.3)  # Darker gray for better visibility
        
        # Branding text
        branding_text = "Powered by @freemindAI"
        
        # Calculate position (bottom center with margin)
        text_width = canvas.stringWidth(branding_text, "Times-Bold", 18)
        text_x = (width - text_width) / 2
        text_y = 25  # Increased margin from bottom
        
        # Draw the branding text
        canvas.drawString(text_x, text_y, branding_text)
    
    def _draw_kdp_image(self, canvas, x, y, width, height, image_data, cover_mode=False):
        """
        Draw an image for KDP pages with proper scaling
        
        Args:
            cover_mode: If True, use 'cover' mode (fill entire area, may crop)
                       If False, use 'fit' mode (fit inside, may have white space)
        """
        try:
            from io import BytesIO
            import base64
            
            # Handle base64 images
            if isinstance(image_data, str) and image_data.startswith('data:image'):
                # Extract base64 data
                header, data = image_data.split(',', 1)
                
                # Fix base64 padding if needed
                missing_padding = len(data) % 4
                if missing_padding:
                    data += '=' * (4 - missing_padding)
                
                image_bytes = base64.b64decode(data)
                image_stream = BytesIO(image_bytes)
                
                # Get image dimensions to maintain aspect ratio
                img_reader = ImageReader(image_stream)
                img_width, img_height = img_reader.getSize()
                
                # Calculate scaling based on mode
                scale_x = width / img_width
                scale_y = height / img_height
                
                if cover_mode:
                    # COVER MODE: Fill entire area (may crop edges)
                    # Use max() to ensure image covers the entire space
                    scale = max(scale_x, scale_y)
                else:
                    # FIT MODE: Fit inside area (may have white space)
                    # Use min() to fit image within bounds
                    scale = min(scale_x, scale_y)
                
                # Calculate scaled dimensions
                scaled_width = img_width * scale
                scaled_height = img_height * scale
                
                # Center the image
                center_x = x + (width - scaled_width) / 2
                center_y = y + (height - scaled_height) / 2
                
                # Draw the image (will be clipped if larger than canvas)
                canvas.drawImage(img_reader, center_x, center_y, scaled_width, scaled_height)
                
        except Exception as e:
            logger.warning(f"Could not draw KDP image: {str(e)}")
            # Fall back to placeholder
            canvas.setFillColorRGB(0.9, 0.9, 0.9)  # Light gray
            canvas.rect(x, y, width, height, fill=1, stroke=1)
            
            canvas.setFont("Times-Bold", 16)
            canvas.setFillColorRGB(0.5, 0.5, 0.5)
            error_text = "Image Error"
            text_width = canvas.stringWidth(error_text, "Times-Bold", 16)
            canvas.drawString(x + (width - text_width) / 2, y + height / 2, error_text)
    
    def _generate_storybook_pdf_reportlab(self, output_path, metadata, pages):
        """
        Generate storybook PDF using ReportLab with title page and story pages
        
        Args:
            output_path: Output file path
            metadata: BookMetadata object
            pages: List of StorybookPage objects
        """
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter, A4, landscape
        from reportlab.lib.colors import black
        import textwrap
        
        # Create PDF canvas - use landscape orientation for spread layout
        page_size = landscape(letter)  # 11" x 8.5" landscape
        logger.info(f"Creating landscape PDF with page size: {page_size}")
        c = canvas.Canvas(output_path, pagesize=page_size)
        width, height = page_size
        
        # Register fonts
        self._register_custom_fonts()
        
        # Page 1: Title Page
        self._draw_title_page(c, width, height, metadata)
        
        # Story Pages - create spreads (2 pages per physical page)
        logger.info(f"Creating {len(pages)} story pages")
        for i, page in enumerate(pages):
            logger.info(f"Drawing story page {i+1}: {page.story_text[:50]}...")
            c.showPage()  # New page
            try:
                self._draw_story_spread(c, width, height, page)
                logger.info(f"Successfully drew story page {i+1}")
            except Exception as e:
                logger.error(f"Error drawing story page {i+1}: {str(e)}")
                # Draw a simple fallback page
                c.setFont("Times-Bold", 24)
                c.setFillColorRGB(0.0, 0.0, 0.0)
                c.drawString(100, height/2, f"Error drawing page {i+1}")
                c.drawString(100, height/2 - 40, str(e))
        
        # Save the PDF
        c.save()
        logger.info(f"Storybook PDF saved: {output_path}")
    
    def _draw_title_page(self, canvas, width, height, metadata):
        """
        Draw the title page with book metadata
        
        Args:
            canvas: ReportLab canvas
            width: Page width
            height: Page height
            metadata: BookMetadata object
        """
        # Title
        canvas.setFont("Times-Bold", 36)
        canvas.setFillColorRGB(0.0, 0.2, 0.8)  # Blue color
        title_width = canvas.stringWidth(metadata.title, "Times-Bold", 36)
        canvas.drawString((width - title_width) / 2, height - 150, metadata.title)
        
        # Subtitle (if exists)
        if metadata.subtitle:
            canvas.setFont("Times-Bold", 24)
            canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
            subtitle_width = canvas.stringWidth(metadata.subtitle, "Times-Bold", 24)
            canvas.drawString((width - subtitle_width) / 2, height - 200, metadata.subtitle)
        
        # Author
        y_pos = height - 250 if metadata.subtitle else height - 220
        canvas.setFont("Times-Bold", 20)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        author_text = f"by {metadata.author}"
        author_width = canvas.stringWidth(author_text, "Times-Bold", 20)
        canvas.drawString((width - author_width) / 2, y_pos, author_text)
        
        # Book Info Box
        box_y = height - 450
        canvas.setFont("Times-Bold", 16)
        canvas.setFillColorRGB(0.0, 0.6, 0.0)  # Green color
        
        # Age Range
        age_text = f"Age Range: {metadata.age_range}"
        canvas.drawString(80, box_y, age_text)
        
        # Theme
        theme_text = f"Theme: {metadata.theme}"
        canvas.drawString(80, box_y - 30, theme_text)
        
        # Moral Lesson
        canvas.setFont("Times-Bold", 14)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        moral_text = f"Moral Lesson: {metadata.moral_lesson}"
        
        # Wrap moral lesson text if too long
        max_width = width - 160  # Leave margins
        if canvas.stringWidth(moral_text, "Times-Bold", 14) > max_width:
            words = moral_text.split()
            lines = []
            current_line = ""
            
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if canvas.stringWidth(test_line, "Times-Bold", 14) <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Draw wrapped lines
            for i, line in enumerate(lines[:3]):  # Max 3 lines
                canvas.drawString(80, box_y - 60 - (i * 20), line)
        else:
            canvas.drawString(80, box_y - 60, moral_text)
        
        # Footer
        canvas.setFont("Times-Roman", 12)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        footer_text = "A Children's Storybook"
        footer_width = canvas.stringWidth(footer_text, "Times-Roman", 12)
        canvas.drawString((width - footer_width) / 2, 80, footer_text)
    
    def _draw_story_spread(self, canvas, width, height, page):
        """
        Draw a children's book spread with illustration on left and text on right
        
        Args:
            canvas: ReportLab canvas
            width: Page width (landscape)
            height: Page height (landscape)
            page: StorybookPage object
        """
        # Calculate spread dimensions
        spread_width = width / 2  # Split the landscape page into two halves
        margin = 40
        
        # LEFT SIDE: Illustration
        self._draw_illustration_side(canvas, 0, 0, spread_width, height, page)
        
        # RIGHT SIDE: Story text with decorative background
        self._draw_text_side(canvas, spread_width, 0, spread_width, height, page)
        
        # Draw center spine line (optional)
        canvas.setStrokeColorRGB(0.9, 0.9, 0.9)  # Light gray
        canvas.setLineWidth(2)
        canvas.line(spread_width, margin, spread_width, height - margin)
    
    def _draw_illustration_side(self, canvas, x, y, width, height, page):
        """
        Draw the left side with illustration/image
        
        Args:
            canvas: ReportLab canvas
            x, y: Position of the left side
            width, height: Dimensions of the left side
            page: StorybookPage object
        """
        margin = 30
        
        # Try to get actual image for this page if available
        image_data = getattr(page, 'image_data', None)
        logger.info(f"Drawing illustration side for page {page.page_number}, image_data available: {image_data is not None}")
        
        if image_data:
            # Draw actual image from HTML content
            self._draw_actual_image(canvas, x + margin, y + margin, width - 2*margin, height - 2*margin, image_data)
        else:
            # Create a colorful and attractive placeholder illustration
            # Gradient-like background with multiple colors
            inner_x = x + margin
            inner_y = y + margin
            inner_width = width - 2*margin
            inner_height = height - 2*margin
            
            # Create a colorful gradient effect with multiple rectangles
            colors = [
                (1.0, 0.9, 0.8),  # Light peach
                (0.9, 1.0, 0.8),  # Light green
                (0.8, 0.9, 1.0),  # Light blue
                (1.0, 0.8, 0.9),  # Light pink
            ]
            
            for i, color in enumerate(colors):
                canvas.setFillColorRGB(*color)
                rect_height = inner_height // 4
                canvas.rect(inner_x, inner_y + i * rect_height, inner_width, rect_height, fill=1, stroke=0)
            
            # Add decorative border
            canvas.setStrokeColorRGB(0.2, 0.4, 0.7)  # Dark blue border
            canvas.setLineWidth(4)
            canvas.roundRect(inner_x, inner_y, inner_width, inner_height, 20, stroke=1, fill=0)
            
            # Add a centered colorful illustration placeholder
            canvas.setFont("Times-Bold", 28)
            canvas.setFillColorRGB(0.1, 0.3, 0.6)  # Dark blue text
            
            # Main title
            main_text = "Kaya the Kangaroo"
            text_width = canvas.stringWidth(main_text, "Times-Bold", 28)
            text_x = x + (width - text_width) / 2
            text_y = y + height / 2 + 40
            
            canvas.drawString(text_x, text_y, main_text)
            
            # Add decorative elements
            canvas.setFont("Times-Bold", 18)
            canvas.setFillColorRGB(0.7, 0.3, 0.1)  # Orange text
            
            subtitle = "Problem-solving Adventure"
            sub_width = canvas.stringWidth(subtitle, "Times-Bold", 18)
            sub_x = x + (width - sub_width) / 2
            sub_y = text_y - 35
            
            canvas.drawString(sub_x, sub_y, subtitle)
            
            # Add some fun decorative shapes
            canvas.setFillColorRGB(1.0, 0.6, 0.2)  # Orange
            # Draw some circles as decorative elements
            canvas.circle(inner_x + 50, inner_y + inner_height - 50, 20, fill=1, stroke=0)
            canvas.circle(inner_x + inner_width - 50, inner_y + 50, 25, fill=1, stroke=0)
            
            canvas.setFillColorRGB(0.3, 0.7, 0.3)  # Green
            canvas.circle(inner_x + inner_width - 80, inner_y + inner_height - 80, 15, fill=1, stroke=0)
            canvas.circle(inner_x + 80, inner_y + 80, 18, fill=1, stroke=0)
            
            # Add a note about the missing image
            canvas.setFont("Times-Roman", 12)
            canvas.setFillColorRGB(0.5, 0.5, 0.5)  # Gray text
            note = "(Image could not be downloaded from URL)"
            note_width = canvas.stringWidth(note, "Times-Roman", 12)
            note_x = x + (width - note_width) / 2
            note_y = sub_y - 50
            
            canvas.drawString(note_x, note_y, note)
    
    def _draw_actual_image(self, canvas, x, y, width, height, image_data):
        """
        Draw an actual image from HTML content
        
        Args:
            canvas: ReportLab canvas
            x, y: Position to draw the image
            width, height: Available space for the image
            image_data: Base64 or URL image data
        """
        logger.info(f"Drawing actual image: {image_data[:100]}...")
        try:
            from io import BytesIO
            import base64
            
            # Handle base64 images
            if isinstance(image_data, str) and image_data.startswith('data:image'):
                # Extract base64 data
                header, data = image_data.split(',', 1)
                
                # Fix base64 padding if needed
                missing_padding = len(data) % 4
                if missing_padding:
                    data += '=' * (4 - missing_padding)
                
                image_bytes = base64.b64decode(data)
                image_stream = BytesIO(image_bytes)
                
                # Get image dimensions to maintain aspect ratio
                img_reader = ImageReader(image_stream)
                img_width, img_height = img_reader.getSize()
                
                # Calculate scaling to fit within available space
                scale_x = width / img_width
                scale_y = height / img_height
                scale = min(scale_x, scale_y)
                
                # Calculate centered position
                scaled_width = img_width * scale
                scaled_height = img_height * scale
                center_x = x + (width - scaled_width) / 2
                center_y = y + (height - scaled_height) / 2
                
                # Draw the image
                canvas.drawImage(img_reader, center_x, center_y, scaled_width, scaled_height)
                
                # Add a subtle border around the image
                canvas.setStrokeColorRGB(0.8, 0.8, 0.8)  # Light gray border
                canvas.setLineWidth(2)
                canvas.roundRect(center_x - 5, center_y - 5, scaled_width + 10, scaled_height + 10, 8, stroke=1, fill=0)
                
        except Exception as e:
            logger.warning(f"Could not draw image: {str(e)}")
            # Fall back to a very visible placeholder
            canvas.setFillColorRGB(1.0, 0.8, 0.8)  # Light pink background
            canvas.rect(x, y, width, height, fill=1, stroke=0)
            
            # Draw a border
            canvas.setStrokeColorRGB(1.0, 0.0, 0.0)  # Red border
            canvas.setLineWidth(3)
            canvas.rect(x, y, width, height, fill=0, stroke=1)
            
            canvas.setFont("Times-Bold", 20)
            canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black text
            error_text = "IMAGE PLACEHOLDER"
            text_width = canvas.stringWidth(error_text, "Times-Bold", 20)
            canvas.drawString(x + (width - text_width) / 2, y + height / 2, error_text)
            
            # Also draw the error for debugging
            canvas.setFont("Times-Roman", 12)
            canvas.setFillColorRGB(0.5, 0.0, 0.0)  # Dark red
            error_detail = f"Error: {str(e)[:50]}"
            detail_width = canvas.stringWidth(error_detail, "Times-Roman", 12)
            canvas.drawString(x + (width - detail_width) / 2, y + height / 2 - 30, error_detail)
    
    def _draw_text_side(self, canvas, x, y, width, height, page):
        """
        Draw the right side with story text and decorative background
        
        Args:
            canvas: ReportLab canvas
            x, y: Position of the right side
            width, height: Dimensions of the right side
            page: StorybookPage object
        """
        margin = 40
        logger.info(f"Drawing text side for page {page.page_number}: '{page.story_text[:50]}...'")
        
        # Create decorative background - professional children's book style
        # Cream/beige background
        canvas.setFillColorRGB(0.98, 0.96, 0.92)  # Warm cream color
        canvas.rect(x + margin, y + margin, width - 2*margin, height - 2*margin, fill=1, stroke=0)
        
        # Add decorative border
        canvas.setStrokeColorRGB(0.9, 0.85, 0.75)  # Warm border
        canvas.setLineWidth(2)
        canvas.roundRect(x + margin, y + margin, width - 2*margin, height - 2*margin, 10, stroke=1, fill=0)
        
        # Draw cute decorative elements (similar to fruit characters in your image)
        self._draw_decorative_elements(canvas, x + margin, y + margin, width - 2*margin, height - 2*margin)
        
        # Main story text area
        text_margin = 60
        text_area_width = width - 2*margin - 2*text_margin
        text_area_height = height - 2*margin - 2*text_margin
        
        # Create a slightly lighter text background
        canvas.setFillColorRGB(0.99, 0.98, 0.95)  # Very light cream
        text_bg_x = x + margin + text_margin - 20
        text_bg_y = y + margin + text_margin - 20
        text_bg_width = text_area_width + 40
        text_bg_height = text_area_height + 40
        
        canvas.roundRect(text_bg_x, text_bg_y, text_bg_width, text_bg_height, 15, fill=1, stroke=0)
        
        # Draw the story text with good readability
        canvas.setFont("Times-Bold", 22)  # Slightly smaller for better fit
        canvas.setFillColorRGB(0.2, 0.2, 0.2)  # Dark gray, easier to read than pure black
        
        # Wrap and center the text
        story_lines = self._wrap_text_to_lines(canvas, page.story_text, "Times-Bold", 22, text_area_width)
        
        # Calculate starting position to center text vertically
        total_text_height = len(story_lines[:6]) * 30  # Max 6 lines
        start_y = y + margin + text_margin + (text_area_height - total_text_height) / 2 + total_text_height
        
        # Draw each line centered
        for i, line in enumerate(story_lines[:6]):
            line_width = canvas.stringWidth(line, "Times-Bold", 22)
            line_x = x + margin + text_margin + (text_area_width - line_width) / 2
            line_y = start_y - (i * 30)
            canvas.drawString(line_x, line_y, line)
        
        # Page number in bottom right
        canvas.setFont("Times-Bold", 16)
        canvas.setFillColorRGB(0.5, 0.5, 0.5)
        page_text = str(page.page_number)
        text_width = canvas.stringWidth(page_text, "Times-Bold", 16)
        canvas.drawString(x + width - margin - text_width - 20, y + margin + 20, page_text)
    
    def _draw_decorative_elements(self, canvas, x, y, width, height):
        """
        Draw cute decorative elements similar to the fruit characters in the reference image
        
        Args:
            canvas: ReportLab canvas
            x, y: Position of the decorative area
            width, height: Dimensions of the decorative area
        """
        # Draw small colorful circles/dots as simple decorative elements
        # (In a full implementation, you could draw actual fruit characters)
        import random
        
        colors = [
            (1.0, 0.6, 0.6),    # Light red
            (0.6, 1.0, 0.6),    # Light green  
            (0.6, 0.6, 1.0),    # Light blue
            (1.0, 1.0, 0.6),    # Light yellow
            (1.0, 0.8, 0.6),    # Light orange
        ]
        
        # Draw decorative elements in corners and edges
        positions = [
            (x + 20, y + height - 30),      # Top left
            (x + width - 30, y + height - 30),  # Top right
            (x + 20, y + 20),               # Bottom left
            (x + width - 30, y + 20),       # Bottom right
            (x + width/2, y + height - 20), # Top center
            (x + width/2, y + 10),          # Bottom center
            (x + 10, y + height/2),         # Left center
            (x + width - 20, y + height/2), # Right center
        ]
        
        for i, (px, py) in enumerate(positions):
            color = colors[i % len(colors)]
            canvas.setFillColorRGB(*color)
            canvas.circle(px, py, 8, fill=1, stroke=0)
            
            # Add a smaller inner circle for detail
            canvas.setFillColorRGB(1.0, 1.0, 1.0)  # White center
            canvas.circle(px, py, 3, fill=1, stroke=0)
    
    def _draw_story_page(self, canvas, width, height, page):
        """
        Legacy method - Draw a story page with text and illustration prompt
        
        Args:
            canvas: ReportLab canvas
            width: Page width
            height: Page height
            page: StorybookPage object
        """
        # Page number
        canvas.setFont("Times-Bold", 14)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        page_text = f"Page {page.page_number}"
        canvas.drawString(width - 100, height - 50, page_text)
        
        # Story Text Area (top half)
        canvas.setFont("Times-Bold", 18)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        
        # Text wrapping for story
        max_width = width - 120  # Leave margins
        story_lines = self._wrap_text_to_lines(canvas, page.story_text, "Times-Bold", 18, max_width)
        
        # Draw story text
        y_position = height - 150
        for line in story_lines[:8]:  # Max 8 lines for story
            canvas.drawString(60, y_position, line)
            y_position -= 25
        
        # Illustration Prompt Section (bottom half)
        separator_y = height // 2 + 50
        
        # Draw separator line
        canvas.setStrokeColorRGB(0.0, 0.0, 0.0)  # Black color
        canvas.setLineWidth(2)
        canvas.line(60, separator_y, width - 60, separator_y)
        
        # Illustration prompt header
        canvas.setFont("Times-Bold", 16)
        canvas.setFillColorRGB(0.0, 0.2, 0.8)  # Blue color
        canvas.drawString(60, separator_y - 40, "Illustration Prompt:")
        
        # Illustration prompt text
        canvas.setFont("Times-Roman", 14)
        canvas.setFillColorRGB(0.0, 0.0, 0.0)  # Black color
        
        prompt_lines = self._wrap_text_to_lines(canvas, page.illustration_prompt, "Times-Roman", 14, max_width)
        
        y_position = separator_y - 70
        for line in prompt_lines[:10]:  # Max 10 lines for prompt
            canvas.drawString(60, y_position, line)
            y_position -= 20
    
    def _extract_images_from_html(self, html_content):
        """
        Extract images from HTML content for use in storybook illustrations
        
        Args:
            html_content: HTML string containing images
            
        Returns:
            list: List of image data (base64 or URLs)
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            images = []
            
            # Find all img tags
            img_tags = soup.find_all('img')
            
            for img in img_tags:
                src = img.get('src', '')
                if src:
                    images.append(src)
            
            # Also look for background images in style attributes
            elements_with_bg = soup.find_all(attrs={'style': True})
            for element in elements_with_bg:
                style = element.get('style', '')
                if 'background-image' in style:
                    # Extract URL from background-image: url(...)
                    import re
                    match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
                    if match:
                        images.append(match.group(1))
            
            # Look for base64 images in div with image-container class
            image_containers = soup.find_all('div', class_='image-container')
            for container in image_containers:
                img = container.find('img')
                if img and img.get('src'):
                    src = img.get('src')
                    if src not in images:  # Avoid duplicates
                        images.append(src)
            
            logger.info(f"Extracted {len(images)} images from HTML content")
            return images
            
        except Exception as e:
            logger.warning(f"Error extracting images from HTML: {str(e)}")
            return []
    
    def _wrap_text_to_lines(self, canvas, text, font_name, font_size, max_width):
        """
        Wrap text into lines that fit within the specified width
        
        Args:
            canvas: ReportLab canvas
            text: Text to wrap
            font_name: Font name
            font_size: Font size
            max_width: Maximum line width
            
        Returns:
            list: List of text lines
        """
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            test_width = canvas.stringWidth(test_line, font_name, font_size)
            
            if test_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
            
        return lines
