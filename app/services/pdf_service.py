"""
PDF generation service using ReportLab
"""
import os
import uuid
import io
import base64
import re
from typing import Optional, Dict, List, Tuple
from pathlib import Path
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
