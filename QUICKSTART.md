# Image Upload Service - Quick Start Guide

## ⚡ 5-Minute Setup

### 1. Prerequisites Check

- [x] Python 3.7 or later
- [x] Docker & Docker Compose
- [x] Git (optional)

### 2. Clone or Download Project

```bash
cd d:\montycloud
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Start LocalStack

```bash
docker-compose up -d
```

Verify it's running:
```bash
docker ps | grep localstack
```

### 5. Create Environment File

Copy the example file:
```bash
cp .env.example .env
```

Or on Windows:
```cmd
copy .env.example .env
```

### 6. Start the API

```bash
python app.py
```

You should see:
```
 * Running on http://0.0.0.0:5000
```

### 7. Test the API

Health check:
```bash
curl http://localhost:5000/health
```

Response:
```json
{"status": "healthy"}
```

## 📤 Quick Test

### Upload an Image

First, create a test image:

**Linux/Mac:**
```bash
python3 << 'EOF'
from PIL import Image
Image.new('RGB', (100, 100), color='red').save('test.jpg')
EOF
```

**Windows:**
```bash
python -c "from PIL import Image; Image.new('RGB', (100, 100), color='red').save('test.jpg')"
```

Then upload it:
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user-123" \
  -F "file=@test.jpg" \
  -F "title=Test Image"
```

Response:
```json
{
  "message": "Image uploaded successfully",
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "s3_key": "images/550e8400-e29b-41d4-a716-446655440000/test.jpg",
  "title": "Test Image",
  "description": "",
  "tags": []
}
```

### List Images

```bash
curl http://localhost:5000/api/v1/images \
  -H "X-User-ID: user-123"
```

## 📝 Run Tests

```bash
pytest test_app.py -v
```

Expected output:
```
test_app.py::TestUploadImage::test_upload_image_success PASSED
test_app.py::TestListImages::test_list_images_by_user PASSED
test_app.py::TestDeleteImage::test_delete_image_success PASSED
...
```

## 🐛 Troubleshooting

### Port Already in Use

If port 5000 is already in use:

```bash
# Find what's using port 5000
lsof -i :5000  # Linux/Mac
netstat -ano | findstr :5000  # Windows

# Use a different port
FLASK_PORT=5001 python app.py
```

### LocalStack Connection Error

```bash
# Restart LocalStack
docker-compose restart

# Or stop and start fresh
docker-compose down
docker-compose up -d
```

### Docker not found

Install Docker from: https://www.docker.com/products/docker-desktop

### Python not found

Install Python from: https://www.python.org/downloads/

## 📚 Next Steps

- Read [README.md](README.md) for full documentation
- Check [TESTING_GUIDE.md](TESTING_GUIDE.md) for detailed testing examples
- Review API endpoints in README.md API Documentation section

## 🚀 Useful Commands

```bash
# View API logs
python app.py

# Run specific test
pytest test_app.py::TestUploadImage::test_upload_image_success -v

# Test with coverage
pytest test_app.py --cov=. --cov-report=html

# List all images in LocalStack S3
aws s3 ls s3://image-uploads/ --endpoint-url http://localhost:4566 --recursive

# View DynamoDB table
aws dynamodb scan --table-name images-metadata --endpoint-url http://localhost:4566
```

## 📊 Project Structure

```
.
├── app.py                 # Flask API endpoints
├── services.py            # AWS service layer
├── config.py              # Configuration
├── test_app.py            # Unit tests (40+ tests)
├── requirements.txt       # Dependencies
├── docker-compose.yml     # LocalStack setup
├── README.md              # Full documentation
├── TESTING_GUIDE.md       # Detailed testing guide
├── QUICKSTART.md          # This file
├── startup.sh             # Linux/Mac startup script
└── startup.bat            # Windows startup script
```

## 🎯 Key Features

✅ Upload images with metadata  
✅ List images with filters (user, tags, title)  
✅ Download/view images  
✅ Update image metadata  
✅ Delete images  
✅ 40+ unit tests  
✅ LocalStack for local development  
✅ AWS-ready code  

## 💡 Tips

- Use `X-User-ID` header in all requests
- Max file size: 10MB
- Supported formats: JPG, PNG, GIF, WebP
- Default query limit: 10 items
- Presigned URLs expire in 1 hour

---

Need help? Check README.md for comprehensive documentation!
