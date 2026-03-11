# Image Upload Service - Code Review Documentation

## Overview

This is an **Instagram-like image upload service** built with Flask, backed by AWS S3 for image storage and DynamoDB for metadata management. **Deployable via AWS SAM** for serverless Lambda execution.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Request                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (SAM)                          │
│           Routes defined in template.yaml                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Lambda Function / Flask App (app.py)               │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │  Health Check   │  │    REST APIs     │  │  Swagger UI    │ │
│  │   /health       │  │  /api/v1/images  │  │   /swagger/    │ │
│  └─────────────────┘  └──────────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│   ImageStorageService   │   │    ImageMetadataService         │
│      (services.py)      │   │       (services.py)             │
└─────────────────────────┘   └─────────────────────────────────┘
            │                               │
            ▼                               ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│       AWS S3            │   │        AWS DynamoDB             │
│  (Image Binary Storage) │   │    (Image Metadata Store)       │
│   (SAM provisioned)     │   │      (SAM provisioned)          │
└─────────────────────────┘   └─────────────────────────────────┘
```

---

## File Structure & Responsibilities

| File | Purpose |
|------|---------|
| `app.py` | Flask application with REST API endpoints + Lambda handler |
| `services.py` | AWS service layer (S3 & DynamoDB operations) |
| `config.py` | Environment configuration & constants |
| `template.yaml` | **AWS SAM template** - Infrastructure as Code |
| `test_app.py` | Comprehensive pytest test suite |
| `requirements.txt` | Python dependencies |
| `run.sh` | Application startup & test script |

---

## Core Components

### 1. Configuration (`config.py`)

Environment-based configuration using `python-dotenv`:

```python
AWS_REGION          = 'ap-south-1'           # Default AWS region
S3_BUCKET_NAME      = 'image-uploads'        # S3 bucket for images
DYNAMODB_TABLE_NAME = 'images-metadata'      # DynamoDB table name
MAX_FILE_SIZE       = 10 * 1024 * 1024       # 10MB max upload
ALLOWED_EXTENSIONS  = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
```

**Key Design Decision:** All configuration is externalized via environment variables, supporting 12-factor app principles.

---

### 2. AWS SAM Template (`template.yaml`)

Infrastructure-as-Code defining all AWS resources:

```yaml
Resources:
  ImageBucket:           # S3 bucket with encryption & CORS
  ImagesMetadataTable:   # DynamoDB with PAY_PER_REQUEST billing
  ImageUploadFunction:   # Lambda function with API Gateway events
  ImageApi:              # API Gateway with binary media support
```

**Key Features:**
- **S3 Bucket:** Server-side encryption (AES256), public access blocked
- **DynamoDB:** PAY_PER_REQUEST billing, Point-in-Time Recovery enabled
- **Lambda:** Auto-generated IAM policies via SAM policy templates
- **API Gateway:** CORS configured, binary media types for images

**Deployment:**
```bash
sam build && sam deploy --guided
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `Environment` | `dev` | Deployment stage (dev/staging/prod) |

**Outputs:**
- `ApiEndpoint` - API Gateway URL
- `ImageBucketName` - S3 bucket name
- `DynamoDBTableName` - DynamoDB table name

---

### 3. Service Layer (`services.py`)

#### AWSClientFactory (Singleton Pattern)
```python
class AWSClientFactory:
    """Factory for creating AWS service clients"""
    _s3_client = None        # Cached S3 client
    _dynamodb_client = None  # Cached DynamoDB client
    _dynamodb_resource = None
```

**Design Pattern:** Singleton pattern ensures single AWS client instances across the application, reducing connection overhead.

#### ImageStorageService (S3 Operations)

| Method | Purpose |
|--------|---------|
| `create_bucket_if_not_exists()` | Auto-provisions S3 bucket (local dev only) |
| `upload_image(data, filename, image_id)` | Uploads image using provided UUID |
| `delete_image(s3_key)` | Removes image from S3 |
| `get_image(s3_key)` | Downloads image binary |
| `generate_presigned_url(s3_key)` | Creates temporary signed URL (1hr default) |

**S3 Key Structure:** `images/{image_id}/{filename}`

**Single UUID Design:** The same `image_id` is used for:
- S3 key path: `images/{image_id}/{filename}`
- DynamoDB partition key: `image_id`

This ensures direct traceability between S3 objects and their metadata.

#### ImageMetadataService (DynamoDB Operations)

**Table Schema:**
| Attribute | Type | Role |
|-----------|------|------|
| `image_id` | String | Partition Key (HASH) |
| `user_id` | String | Sort Key (RANGE) |
| `s3_key` | String | Reference to S3 object |
| `title` | String | Image title |
| `description` | String | Image description |
| `tags` | List | Searchable tags |
| `created_at` | String (ISO) | Creation timestamp |
| `updated_at` | String (ISO) | Last modified timestamp |

**Global Secondary Indexes (GSIs):**
1. `user_id-created_at-index` - Query images by user, sorted by date
2. `title-created_at-index` - Search images by exact title match

---

### 3. REST API (`app.py`)

#### Authentication
All endpoints (except `/health`) require `X-User-ID` header:
```python
@validate_request()  # Decorator validates X-User-ID presence
def endpoint():
    user_id = request.headers.get('X-User-ID')
```

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (returns `{"status": "healthy"}`) |
| `POST` | `/api/v1/images/upload` | Upload image with metadata |
| `GET` | `/api/v1/images` | List/filter images |
| `GET` | `/api/v1/images/<id>` | Download specific image |
| `PUT` | `/api/v1/images/<id>` | Update image metadata |
| `DELETE` | `/api/v1/images/<id>` | Delete image and metadata |

#### Upload Flow (POST /api/v1/images/upload)

```
1. Validate X-User-ID header present
2. Validate file exists and has allowed extension
3. Check file size ≤ 10MB
4. Upload to S3 (get s3_key)
5. Save metadata to DynamoDB
6. If DynamoDB fails → Rollback: delete from S3
7. Return success with image_id, s3_key
```

**Transactional Behavior:** If metadata save fails, the S3 image is deleted (rollback).

#### List/Filter Options (GET /api/v1/images)

| filter_by | Parameters | Query Method |
|-----------|------------|--------------|
| `user` (default) | `user_id` | GSI query on `user_id-created_at-index` |
| `tags` | `tags` (comma-separated) | Filter after user query |
| `title` | `title` | GSI query on `title-created_at-index` |

---

### 4. API Documentation (Swagger)

- **Swagger UI:** Available at `/swagger/`
- **OpenAPI Spec:** Available at `/apispec.json`
- All endpoints documented with Flasgger decorators

---

## Error Handling

| HTTP Code | Scenario |
|-----------|----------|
| 400 | Missing file, invalid extension, missing required params |
| 401 | Missing X-User-ID header |
| 404 | Image not found |
| 413 | File exceeds 10MB limit |
| 500 | S3/DynamoDB operation failures |

Global error handlers for 404, 413, and 500 ensure consistent JSON responses.

---

## Testing Strategy (`test_app.py`)

### Test Infrastructure
- **Mocking:** Uses `unittest.mock.patch` to isolate AWS calls
- **Fixtures:**
  - `client` - Flask test client
  - `reset_aws_factory` - Resets singleton clients between tests

### Test Coverage

| Test Class | Coverage |
|------------|----------|
| `TestHealthCheck` | Health endpoint |
| `TestUploadImage` | Upload success, validation errors, S3 failures, rollback |
| `TestListImages` | Filter by user/tags/title, pagination |
| `TestGetImage` | Download, 404 handling |
| `TestDeleteImage` | Delete success, authorization |
| `TestUpdateMetadata` | Metadata updates |

### Key Test Scenarios
- ✅ All allowed file extensions work
- ✅ Rollback on metadata failure (S3 image deleted)
- ✅ Missing headers return 401
- ✅ Invalid file types return 400
- ✅ Large files return 413

---

## Security Considerations

| Aspect | Implementation |
|--------|----------------|
| Authentication | Header-based (`X-User-ID`) - **Note: Not production-ready** |
| Authorization | Users can only manage their own images |
| File Validation | Extension whitelist, size limit |
| URL Signing | Presigned URLs expire in 1 hour |
| Input Sanitization | `secure_filename()` for uploads |

**Recommendation for Production:** Replace X-User-ID with proper JWT/OAuth authentication.

---

## Performance Considerations

1. **Lazy Resource Initialization**
   ```python
   @app.before_request
   def initialize_aws_resources():
       if not hasattr(app, 'resources_initialized'):
           # Create bucket/table only on first request
   ```

2. **Connection Reuse:** Singleton pattern for AWS clients

3. **DynamoDB Indexes:** GSIs enable efficient queries without table scans

4. **Presigned URLs:** Offload image serving to S3 directly

---

## How to Run

### Prerequisites
```bash
pip install -r requirements.txt
```

### Environment Variables (optional)
```bash
export AWS_REGION=ap-south-1
export S3_BUCKET_NAME=my-bucket
export DYNAMODB_TABLE_NAME=my-table
export FLASK_ENV=development
```

### Start Server
```bash
./run.sh start
# Server runs on http://0.0.0.0:5000
```

### Run Tests
```bash
pytest test_app.py -v
```

---

## API Usage Examples

### Upload Image
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user123" \
  -F "file=@photo.jpg" \
  -F "title=My Photo" \
  -F "description=Beautiful sunset" \
  -F "tags=nature,sunset"
```

### List User's Images
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=user&limit=10" \
  -H "X-User-ID: user123"
```

### Search by Tags
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=tags&tags=nature,sunset" \
  -H "X-User-ID: user123"
```

### Delete Image
```bash
curl -X DELETE http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-User-ID: user123"
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| boto3 | AWS SDK for Python |
| flasgger | Swagger UI integration |
| python-dotenv | Environment variable loading |
| Pillow | Image processing (available for future use) |
| pytest + moto | Testing with AWS mocks |

---

## Areas for Improvement (Discussion Points)

1. **Authentication:** Current X-User-ID header is not secure for production
2. **Tag Search:** Uses client-side filtering; could use DynamoDB GSI on tags
3. **Content-Type Detection:** Currently hardcoded as `image/jpeg`
4. **Pagination:** Implement cursor-based pagination for large datasets
5. **Caching:** Add Redis/CloudFront for frequently accessed images
6. **Image Processing:** Pillow is included but not used (could add thumbnails)

---

## Summary

This service provides a clean, well-structured REST API for image management with:
- **Separation of concerns:** Config → Services → API layers
- **AWS best practices:** Lazy initialization, connection pooling, GSIs
- **Comprehensive testing:** 80%+ code coverage with mocked AWS services
- **Developer experience:** Swagger documentation, clear error messages
