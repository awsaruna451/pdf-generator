"""
Simple test script to demonstrate PDF Generator API functionality
"""
import requests
import json
import time


def test_pdf_generation():
    """Test the PDF generation API"""
    base_url = "http://localhost:8000"
    
    # Test HTML content
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test PDF</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; border-bottom: 2px solid #333; }
            .content { margin: 20px 0; }
            .footer { margin-top: 50px; font-size: 12px; color: #666; }
        </style>
    </head>
    <body>
        <h1>PDF Generator API Test</h1>
        <div class="content">
            <p>This is a test PDF generated using the FastAPI PDF Generator.</p>
            <p>Features tested:</p>
            <ul>
                <li>HTML to PDF conversion</li>
                <li>Custom styling with CSS</li>
                <li>FastAPI integration</li>
                <li>File download functionality</li>
            </ul>
        </div>
        <div class="footer">
            <p>Generated on: {}</p>
        </div>
    </body>
    </html>
    """.format(time.strftime("%Y-%m-%d %H:%M:%S"))
    
    print("Testing PDF Generator API...")
    print("=" * 50)
    
    # Test 1: Health Check
    print("1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/api/v1/pdf/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    print()
    
    # Test 2: Generate PDF
    print("2. Testing PDF generation...")
    try:
        payload = {
            "html_content": html_content,
            "filename": "test_document"
        }
        
        response = requests.post(
            f"{base_url}/api/v1/pdf/generate",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            result = response.json()
            print("✅ PDF generation successful")
            print(f"   Filename: {result['filename']}")
            print(f"   Download URL: {result['download_url']}")
            
            # Test 3: Download PDF
            print("\n3. Testing PDF download...")
            download_url = f"{base_url}{result['download_url']}"
            download_response = requests.get(download_url)
            
            if download_response.status_code == 200:
                with open(result['filename'], 'wb') as f:
                    f.write(download_response.content)
                print(f"✅ PDF downloaded successfully: {result['filename']}")
            else:
                print(f"❌ PDF download failed: {download_response.status_code}")
                
        else:
            print(f"❌ PDF generation failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except Exception as e:
        print(f"❌ PDF generation error: {e}")
    
    print()
    
    # Test 4: List PDFs
    print("4. Testing PDF list...")
    try:
        response = requests.get(f"{base_url}/api/v1/pdf/list")
        if response.status_code == 200:
            result = response.json()
            print("✅ PDF list retrieved")
            print(f"   Total files: {result['count']}")
            for file_info in result['files']:
                print(f"   - {file_info['filename']} ({file_info['size_bytes']} bytes)")
        else:
            print(f"❌ PDF list failed: {response.status_code}")
    except Exception as e:
        print(f"❌ PDF list error: {e}")
    
    print()
    print("=" * 50)
    print("Test completed!")


if __name__ == "__main__":
    test_pdf_generation()
