# Instagram-like Image Upload Service

A scalable, cloud-based image upload and storage service built with Python, AWS services (Lambda, S3, DynamoDB), and LocalStack for local development.

## Project Overview

This service provides RESTful APIs for uploading, managing, and retrieving images with metadata. It's designed to handle multiple concurrent users with scalability in mind using:

- **API Gateway**: HTTP request routing (simulated by Flask)
- **Lambda Functions**: Serverless compute (simulated by Flask endpoints)
- **S3**: Image storage
- **DynamoDB**: NoSQL metadata storage
- **LocalStack**: Local AWS emulation for development

## Project Structure

```
.
├── app.py                 # Flask application with API endpoints
├── services.py            # AWS service layer (S3, DynamoDB operations)
├── config.py              # Configuration and environment variables
├── test_app.py            # Comprehensive unit tests
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # LocalStack configuration
└── README.md              # This file
```

## Setup Instructions

### Prerequisites

- Python 3.7+
- Docker and Docker Compose
- pip (Python package manager)

### 1. Start LocalStack

LocalStack provides a local AWS environment for development and testing without needing actual AWS credentials.

```bash
docker-compose up -d
```

Verify LocalStack is running:
```bash
docker ps | grep localstack
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
LOCALSTACK_ENDPOINT=http://localhost:4566
S3_BUCKET_NAME=image-uploads
DYNAMODB_TABLE_NAME=images-metadata
FLASK_ENV=development
```

### 4. Run the Application

```bash
python app.py
```

The API will be available at `http://localhost:5000`

## API Documentation

### Authentication

All endpoints (except `/health`) require the `X-User-ID` header:

```
X-User-ID: user-123
```

### Base URL

```
http://localhost:5000/api/v1
```

---

## API Endpoints

### 1. Upload Image

**Endpoint:** `POST /images/upload`

**Description:** Upload an image with optional metadata

**Headers:**
```
X-User-ID: user-123
```

**Request Body (multipart/form-data):**
- `file` (required): Image file (jpg, jpeg, png, gif, webp)
- `title` (optional): Image title (default: "Untitled")
- `description` (optional): Image description
- `tags` (optional): Comma-separated tags (e.g., "vacation, beach")

**Example:**
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user-123" \
  -F "file=@/path/to/image.jpg" \
  -F "title=My Vacation" \
  -F "description=Beach photo from summer" \
  -F "tags=vacation, beach, summer"
```

**Response (201 Created):**
```json
{
  "message": "Image uploaded successfully",
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "s3_key": "images/550e8400-e29b-41d4-a716-446655440000/image.jpg",
  "title": "My Vacation",
  "description": "Beach photo from summer",
  "tags": ["vacation", "beach", "summer"]
}
```

**Error Responses:**
- `400 Bad Request`: No file provided, invalid format, or file too large
- `401 Unauthorized`: Missing X-User-ID header
- `413 Payload Too Large`: File exceeds 10MB limit
- `500 Internal Server Error`: Upload or metadata save failed

---

### 2. List Images

**Endpoint:** `GET /images`

**Description:** List images with support for multiple filters

**Headers:**
```
X-User-ID: user-123
```

**Query Parameters:**
- `filter_by` (optional): Filter type - `user` (default), `tags`, or `title`
- `user_id` (optional): User ID to filter by (default: current user)
- `tags` (optional): Comma-separated tags to search (required if `filter_by=tags`)
- `title` (optional): Title to search (required if `filter_by=title`)
- `limit` (optional): Max results to return (default: 10, max: 100)

**Examples:**

#### List user's images (default):
```bash
curl -X GET "http://localhost:5000/api/v1/images" \
  -H "X-User-ID: user-123"
```

#### Search by tags:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=tags&tags=vacation,beach&limit=5" \
  -H "X-User-ID: user-123"
```

#### Search by title:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=title&title=Vacation" \
  -H "X-User-ID: user-123"
```

#### List another user's images:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=user&user_id=user-456" \
  -H "X-User-ID: user-123"
```

**Response (200 OK):**
```json
{
  "count": 2,
  "filter": "user",
  "images": [
    {
      "image_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "user-123",
      "title": "My Vacation",
      "description": "Beach photo",
      "tags": ["vacation", "beach"],
      "s3_key": "images/550e8400-e29b-41d4-a716-446655440000/image.jpg",
      "created_at": "2024-01-04T10:30:00.000000",
      "updated_at": "2024-01-04T10:30:00.000000",
      "url": "http://localhost:4566/image-uploads/images/550e8400-e29b-41d4-a716-446655440000/image.jpg?..."
    }
  ]
}
```

---

### 3. Get/Download Image

**Endpoint:** `GET /images/<image_id>`

**Description:** Download or view a specific image

**Headers:**
```
X-User-ID: user-123
```

**Path Parameters:**
- `image_id` (required): Image ID from upload response

**Example:**
```bash
curl -X GET "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123" \
  -o downloaded_image.jpg
```

**Response (200 OK):**
- Binary image file with headers:
  - `Content-Type: image/jpeg`
  - `Content-Disposition: attachment; filename="..."` (if downloading)

**Error Responses:**
- `401 Unauthorized`: Missing X-User-ID header
- `404 Not Found`: Image does not exist
- `500 Internal Server Error`: Retrieval failed

---

### 4. Delete Image

**Endpoint:** `DELETE /images/<image_id>`

**Description:** Delete an image and its metadata

**Headers:**
```
X-User-ID: user-123
```

**Path Parameters:**
- `image_id` (required): Image ID to delete

**Example:**
```bash
curl -X DELETE "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123"
```

**Response (200 OK):**
```json
{
  "message": "Image deleted successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing X-User-ID header
- `404 Not Found`: Image does not exist
- `500 Internal Server Error`: Deletion failed

---

### 5. Update Image Metadata

**Endpoint:** `PUT /images/<image_id>`

**Description:** Update image metadata (title, description, tags)

**Headers:**
```
X-User-ID: user-123
Content-Type: application/json
```

**Path Parameters:**
- `image_id` (required): Image ID to update

**Request Body (JSON):**
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "tags": ["new-tag1", "new-tag2"]
}
```

(All fields are optional)

**Example:**
```bash
curl -X PUT "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Vacation Photo",
    "tags": ["updated", "vacation"]
  }'
```

**Response (200 OK):**
```json
{
  "message": "Metadata updated successfully"
}
```

**Error Responses:**
- `401 Unauthorized`: Missing X-User-ID header
- `404 Not Found`: Image does not exist
- `500 Internal Server Error`: Update failed

---

### 6. Health Check

**Endpoint:** `GET /health`

**Description:** Check API health status

**Example:**
```bash
curl -X GET "http://localhost:5000/health"
```

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

---

## Running Tests

The project includes comprehensive unit tests covering all API endpoints and service layer functionality.

### Run all tests:
```bash
pytest test_app.py -v
```

### Run with coverage:
```bash
pytest test_app.py --cov=. --cov-report=html
```

### Run specific test class:
```bash
pytest test_app.py::TestUploadImage -v
```

### Run specific test:
```bash
pytest test_app.py::TestUploadImage::test_upload_image_success -v
```

**Test Coverage:**

- **Upload Tests** (5 tests)
  - Missing X-User-ID header
  - No file provided
  - Invalid file type
  - Successful upload
  - Metadata save failure and rollback

- **List Tests** (4 tests)
  - Missing X-User-ID header
  - Filter by user
  - Filter by tags
  - Filter by title

- **Get Tests** (3 tests)
  - Missing X-User-ID header
  - Image not found
  - Successful retrieval

- **Delete Tests** (3 tests)
  - Missing X-User-ID header
  - Image not found
  - Successful deletion

- **Update Tests** (3 tests)
  - Missing X-User-ID header
  - Image not found
  - Successful update

- **Service Layer Tests** (6 tests)
  - S3 upload
  - S3 deletion
  - DynamoDB save
  - DynamoDB retrieval
  - And more...

---

## Architecture & Scalability

### Service Layer Design

The application uses a **two-tier service architecture**:

1. **ImageStorageService** - Handles S3 operations
   - Upload images with unique S3 keys
   - Delete images
   - Retrieve images
   - Generate presigned URLs for secure access

2. **ImageMetadataService** - Handles DynamoDB operations
   - Save/retrieve/update metadata
   - Support multiple filters (user, tags, title)
   - Uses Global Secondary Indexes (GSIs) for efficient querying

### Scalability Features

1. **Stateless API Layer**: Flask instances can be horizontally scaled
2. **Global Secondary Indexes**: Optimize queries by user, tags, or title
3. **Presigned URLs**: Direct S3 access without going through the API
4. **Asynchronous Operations**: S3 uploads/downloads are handled efficiently
5. **Connection Pooling**: AWS SDK handles connection reuse

### Database Design

**Primary Key:** 
- Partition Key: `image_id` (UUID)
- Sort Key: `user_id`

**Global Secondary Indexes:**
1. `user_id-created_at-index`: Query images by user
2. `title-created_at-index`: Search images by title

This design allows:
- ✅ Query all images for a user
- ✅ Search by title
- ✅ Filter by tags (with in-memory filtering)
- ✅ Sorted by creation time

---

## Configuration Details

### Environment Variables (`.env`)

```env
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# LocalStack
LOCALSTACK_ENDPOINT=http://localhost:4566

# S3
S3_BUCKET_NAME=image-uploads
MAX_FILE_SIZE=10485760  # 10MB

# DynamoDB
DYNAMODB_TABLE_NAME=images-metadata

# Flask
FLASK_ENV=development
DEBUG=true
```

### Supported Image Formats
- JPG/JPEG
- PNG
- GIF
- WebP

### File Size Limits
- Maximum file size: 10 MB (configurable)

---

## Development Workflow

### 1. Local Development

Start LocalStack:
```bash
docker-compose up -d
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Run the application:
```bash
python app.py
```

Run tests:
```bash
pytest test_app.py -v
```

### 2. Testing Against Live Services

The test suite uses mocking to avoid making actual AWS calls:

```python
@patch('app.storage_service.upload_image')
def test_upload_image_success(self, mock_upload, client):
    mock_upload.return_value = 'images/uuid/test.jpg'
    # ... test code
```

### 3. Production Deployment

To deploy to AWS:

1. Remove LocalStack endpoint configuration
2. Update AWS credentials with actual IAM user credentials
3. Ensure S3 bucket and DynamoDB table exist
4. Deploy using:
   - AWS Lambda with API Gateway
   - EC2 with Elastic Load Balancer
   - ECS/Fargate with ALB

---

## Troubleshooting

### LocalStack Connection Issues

**Problem:** `Connection refused on port 4566`

**Solution:**
```bash
# Verify LocalStack is running
docker-compose ps

# Check logs
docker-compose logs localstack

# Restart LocalStack
docker-compose restart
```

### AWS Credentials Error

**Problem:** `InvalidCredentialsError` or `NoCredentialsError`

**Solution:**
Ensure `.env` file contains:
```env
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

### File Upload Fails

**Problem:** `Failed to upload image to storage`

**Solution:**
1. Check S3 bucket exists: `aws s3 ls --endpoint-url http://localhost:4566`
2. Check file size: Must be < 10MB
3. Check file format: Only jpg, png, gif, webp allowed

### Tests Failing

**Problem:** `ModuleNotFoundError` or `ImportError`

**Solution:**
```bash
# Verify all dependencies installed
pip install -r requirements.txt

# Run with verbose output
pytest test_app.py -vv
```

---

## Performance Considerations

1. **DynamoDB Capacity**: Default provisioned throughput is 5 RCU/WCU. Adjust for production load
2. **S3 Performance**: Use S3 Transfer Acceleration for faster uploads
3. **Query Limits**: Default query limit is 10 items, max 100
4. **Presigned URLs**: Default expiration is 1 hour (3600 seconds)
5. **Connection Pooling**: AWS SDK automatically manages connection pools

---

## Security Best Practices

1. **Authentication**: Use API Gateway with AWS IAM or Cognito in production
2. **Authorization**: Validate user_id on all operations
3. **Encryption**: Enable S3 server-side encryption
4. **Access Control**: Use S3 bucket policies and DynamoDB encryption at rest
5. **Presigned URLs**: Set appropriate expiration times
6. **HTTPS**: Use HTTPS in production (not HTTP)
7. **Logging**: CloudWatch logs for audit trails

---

## Future Enhancements

- [ ] Image resizing and thumbnails using Lambda
- [ ] Facial recognition using Rekognition
- [ ] Full-text search using CloudSearch/Elasticsearch
- [ ] Image optimization and compression
- [ ] Rate limiting and throttling
- [ ] Multi-region replication
- [ ] Lifecycle policies for old images
- [ ] Cost optimization with S3 Intelligent-Tiering

---

## License

MIT License - See LICENSE file for details

---

## Support

For issues, questions, or contributions, please refer to the project documentation or contact the development team.
