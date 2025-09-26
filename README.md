# PDF Generator API

A FastAPI application for generating PDFs from HTML content using pdfkit. This API provides endpoints to convert HTML strings or files to PDF format with customizable options.

## Features

- 🚀 **FastAPI Framework**: Modern, fast web framework for building APIs
- 📄 **PDF Generation**: Convert HTML content to PDF using pdfkit
- 🔒 **Input Validation**: Pydantic models for request/response validation
- 📁 **File Management**: Generate, download, and list PDF files
- 🛡️ **Error Handling**: Comprehensive error handling and logging
- 📚 **API Documentation**: Auto-generated OpenAPI/Swagger documentation
- 🔧 **Configurable**: Environment-based configuration
- 🧪 **Production Ready**: Proper logging, CORS, and security features

## Prerequisites

Before running this application, make sure you have:

1. **Python 3.8+** installed
2. **wkhtmltopdf** installed on your system

### Installing wkhtmltopdf

#### macOS
```bash
brew install wkhtmltopdf
```

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install wkhtmltopdf
```

#### Windows
Download and install from: https://wkhtmltopdf.org/downloads.html

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd pdf-generator
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv myvoice
   source myvoice/bin/activate  # On Windows: myvoice\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables** (optional)
   ```bash
   cp .env.example .env
   # Edit .env file with your configuration
   ```

## Usage

### Running the Application

1. **Development mode**
   ```bash
   python -m app.main
   ```

2. **Using uvicorn directly**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Production mode**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

The API will be available at:
- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### 1. Health Check
```http
GET /api/v1/pdf/health
```

### 2. Generate PDF from HTML String
```http
POST /api/v1/pdf/generate
Content-Type: application/json

{
  "html_content": "<html><body><h1>Hello World</h1><p>This is a test PDF.</p></body></html>",
  "filename": "my_document"
}
```

### 3. Generate PDF from HTML File
```http
POST /api/v1/pdf/generate-from-file
Content-Type: application/json

{
  "html_file_path": "/path/to/file.html",
  "filename": "my_document"
}
```

### 4. Download PDF
```http
GET /api/v1/pdf/download/{filename}
```

### 5. List Generated PDFs
```http
GET /api/v1/pdf/list
```

## Example Usage

### Using curl

1. **Generate PDF from HTML string**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/pdf/generate" \
        -H "Content-Type: application/json" \
        -d '{
          "html_content": "<html><body><h1>Hello World</h1><p>This is a test PDF generated from HTML string.</p></body></html>",
          "filename": "hello_world"
        }'
   ```

2. **Download the generated PDF**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/pdf/download/hello_world.pdf" \
        --output hello_world.pdf
   ```

### Using Python requests

```python
import requests

# Generate PDF
response = requests.post(
    "http://localhost:8000/api/v1/pdf/generate",
    json={
        "html_content": "<html><body><h1>Hello World</h1><p>This is a test PDF.</p></body></html>",
        "filename": "test_pdf"
    }
)

if response.status_code == 201:
    result = response.json()
    print(f"PDF generated: {result['filename']}")
    
    # Download the PDF
    download_response = requests.get(f"http://localhost:8000{result['download_url']}")
    with open(result['filename'], 'wb') as f:
        f.write(download_response.content)
    print("PDF downloaded successfully!")
```

## Configuration

The application can be configured using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Host to bind the server |
| `PORT` | `8000` | Port to bind the server |
| `DEBUG` | `false` | Enable debug mode |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins (comma-separated) |
| `OUTPUT_DIR` | `output` | Directory to store generated PDFs |
| `SECRET_KEY` | `your-secret-key-change-in-production` | Secret key for security |

## Project Structure

```
pdf-generator/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── pdf_routes.py   # PDF API routes
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py           # Configuration settings
│   ├── models/
│   │   ├── __init__.py
│   │   └── pdf_models.py       # Pydantic models
│   └── services/
│       ├── __init__.py
│       └── pdf_service.py      # PDF generation service
├── output/                     # Generated PDFs (created automatically)
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables example
├── .gitignore                 # Git ignore file
└── README.md                  # This file
```

## Error Handling

The API includes comprehensive error handling:

- **400 Bad Request**: Invalid request data
- **404 Not Found**: File not found
- **422 Unprocessable Entity**: Validation errors
- **500 Internal Server Error**: Server errors

All errors return a consistent JSON format:
```json
{
  "success": false,
  "message": "Error description",
  "error_code": "ERROR_CODE"
}
```

## Security Features

- Input validation using Pydantic models
- Filename sanitization to prevent path traversal
- CORS configuration
- Optional authentication support (Bearer token)
- Error message sanitization

## Development

### Code Style

The project follows Python best practices:
- Type hints throughout the codebase
- Pydantic for data validation
- Proper error handling and logging
- Clean separation of concerns

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black app/
isort app/
flake8 app/
```

## Troubleshooting

### Common Issues

1. **wkhtmltopdf not found**
   - Make sure wkhtmltopdf is installed and in your PATH
   - On some systems, you may need to specify the path in pdfkit configuration

2. **Permission errors**
   - Ensure the application has write permissions to the output directory
   - Check file permissions for generated PDFs

3. **Memory issues with large HTML**
   - Consider chunking large HTML content
   - Monitor system memory usage

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please open an issue in the repository.
