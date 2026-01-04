# Architecture & Design Documentation

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Layer                            │
│  (Web Browser, Mobile App, Desktop Client)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              API Gateway / Load Balancer                     │
│  (HTTP/HTTPS, Authentication, Rate Limiting)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         Flask Application (API Endpoints)                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  • Upload Image                                      │   │
│  │  • List Images (with filters)                        │   │
│  │  • Get Image                                         │   │
│  │  • Update Metadata                                   │   │
│  │  • Delete Image                                      │   │
│  └──────────────────────────────────────────────────────┘   │
└────────┬────────────────────────────────────────────┬───────┘
         │                                            │
         ▼                                            ▼
┌──────────────────────────┐            ┌──────────────────────┐
│   S3 Storage Service     │            │ DynamoDB Metadata    │
│  (Image Files)           │            │ (JSON Documents)     │
│                          │            │                      │
│ • image-uploads bucket   │            │ • images-metadata    │
│ • Organized by user ID   │            │ • GSI: user-id       │
│ • Versioning enabled     │            │ • GSI: title         │
└──────────────────────────┘            └──────────────────────┘
```

## Data Flow Diagrams

### Upload Image Flow

```
1. Client Request
   ├─ File: Binary image data
   ├─ Metadata: Title, Description, Tags
   └─ Header: X-User-ID

2. Validation Layer
   ├─ Verify user ID
   ├─ Validate file format
   └─ Check file size

3. Storage Phase
   ├─ Upload to S3
   │  └─ S3 Key: images/{uuid}/{filename}
   │
   └─ Save to DynamoDB
      ├─ image_id (PK)
      ├─ user_id (SK)
      ├─ title, description
      ├─ tags
      └─ timestamps

4. Response
   └─ image_id, S3 key, presigned URL
```

### List Images Flow

```
1. Client Request
   ├─ Filter Type: user|tags|title
   ├─ Filter Values: [params]
   └─ Header: X-User-ID

2. Query Selection
   ├─ filter_by == 'user'
   │  └─ Query GSI: user_id-created_at
   │
   ├─ filter_by == 'tags'
   │  ├─ Query GSI: user_id-created_at
   │  └─ Filter results by tags (in-memory)
   │
   └─ filter_by == 'title'
      └─ Query GSI: title-created_at

3. Response Enrichment
   ├─ For each item:
   │  ├─ Add presigned URL
   │  └─ Format metadata
   │
   └─ Return paginated results
```

### Download Image Flow

```
1. Client Request
   ├─ image_id
   └─ Header: X-User-ID

2. Lookup
   ├─ Query DynamoDB
   │  └─ Get S3 key from metadata
   │
   └─ Verify ownership
      └─ user_id matches

3. Download
   └─ Get from S3
      └─ Return binary data

4. Response
   └─ Image file with headers
```

## Database Design

### DynamoDB Table: images-metadata

**Partition Key (HASH):** `image_id` (String, UUID)  
**Sort Key (RANGE):** `user_id` (String)

#### Primary Index

```
image_id (HASH) | user_id (RANGE)
─────────────────────────────────
img-123         | user-456
img-124         | user-456
img-125         | user-789
```

#### Global Secondary Index: user_id-created_at-index

```
user_id (HASH) | created_at (RANGE)
──────────────────────────────────────
user-456       | 2024-01-04T10:00:00 ← Latest
user-456       | 2024-01-04T09:00:00
user-456       | 2024-01-04T08:00:00
user-789       | 2024-01-04T10:30:00
```

**Use Case:** Query all images for a user, sorted by creation time

#### Global Secondary Index: title-created_at-index

```
title (HASH)    | created_at (RANGE)
────────────────────────────────────────
Vacation        | 2024-01-04T10:00:00
Beach           | 2024-01-04T09:00:00
Sunset          | 2024-01-04T08:00:00
```

**Use Case:** Search images by title, sorted by creation time

### Document Structure

```json
{
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "s3_key": "images/550e8400-e29b-41d4-a716-446655440000/vacation.jpg",
  "title": "My Vacation Photo",
  "description": "Beautiful beach sunset",
  "tags": ["vacation", "beach", "sunset"],
  "created_at": "2024-01-04T10:30:00.000000",
  "updated_at": "2024-01-04T10:30:00.000000"
}
```

## Service Layer Architecture

### ImageStorageService (S3 Operations)

```python
ImageStorageService
├── create_bucket_if_not_exists()
├── upload_image(data, filename) → s3_key
├── delete_image(s3_key) → bool
├── get_image(s3_key) → bytes
└── generate_presigned_url(s3_key) → url
```

**Responsibilities:**
- S3 bucket management
- File upload/download
- Presigned URL generation
- Error handling and logging

### ImageMetadataService (DynamoDB Operations)

```python
ImageMetadataService
├── create_table_if_not_exists()
├── save_metadata(...) → bool
├── get_image_metadata(image_id, user_id) → dict
├── list_images_by_user(user_id) → [dict]
├── search_images_by_title(title) → [dict]
├── search_images_by_tags(user_id, tags) → [dict]
├── update_metadata(...) → bool
└── delete_metadata(image_id, user_id) → bool
```

**Responsibilities:**
- Table management
- CRUD operations
- Complex queries via GSI
- Result filtering and pagination

## API Endpoint Architecture

### Request/Response Pattern

```
Request
├── Headers
│  └── X-User-ID: Identifies the user
├── Path Parameters
│  └── /api/v1/images/{image_id}
├── Query Parameters
│  └── ?filter_by=user&limit=10
└── Body (if POST/PUT)
   └── JSON or multipart/form-data

Response
├── Status Code
│  ├── 200: Success
│  ├── 201: Created
│  ├── 400: Bad Request
│  ├── 401: Unauthorized
│  ├── 404: Not Found
│  └── 500: Server Error
└── Body
   ├── JSON object/array
   └── Or binary (image data)
```

### Error Handling Strategy

```
Exception
    ├─ Validation Error (400)
    │  └─ Invalid file type, missing params
    │
    ├─ Authorization Error (401)
    │  └─ Missing X-User-ID header
    │
    ├─ Not Found Error (404)
    │  └─ Image doesn't exist
    │
    └─ Server Error (500)
       ├─ S3 connection failure
       ├─ DynamoDB failure
       └─ Unexpected exception
```

## Scalability Design

### Horizontal Scaling

```
┌──────────────────────────────────────┐
│      API Gateway / Load Balancer     │
└──────────┬────────────────┬──────────┘
           │                │
      ┌────▼───┐      ┌────▼───┐
      │ Flask  │      │ Flask  │
      │  App 1 │      │  App 2 │ ... (Auto-scaling)
      └────┬───┘      └────┬───┘
           │                │
           └────────┬───────┘
                    │
           ┌────────▼────────┐
           │   S3 (Managed)  │
           │ DynamoDB (Auto) │
           └─────────────────┘
```

**Features:**
- Stateless API layer (can scale horizontally)
- AWS-managed S3 and DynamoDB (auto-scaling)
- Load balancer distributes requests
- Session storage (metadata) independent of API instance

### Performance Optimization

1. **DynamoDB:**
   - Global Secondary Indexes for efficient queries
   - Provisioned throughput scales with demand
   - Point-in-time recovery for data protection

2. **S3:**
   - Object versioning enabled
   - Lifecycle policies for cost optimization
   - Transfer acceleration for faster uploads

3. **API:**
   - Presigned URLs for direct S3 access
   - Pagination to limit response sizes
   - Connection pooling for AWS SDK

4. **Caching (Future):**
   - CloudFront for image delivery
   - ElastiCache for metadata queries
   - API response caching

## Security Architecture

### Authentication & Authorization

```
User Request
    │
    ▼
┌──────────────────────┐
│ API Gateway Auth     │
│ (Check headers)      │
└──────────────────────┘
    │
    ├─ Valid X-User-ID?
    │  └─ Yes → Proceed
    │  └─ No → 401 Unauthorized
    │
    ▼
┌──────────────────────┐
│ Service Layer Auth   │
│ (Verify ownership)   │
└──────────────────────┘
    │
    ├─ User owns image?
    │  └─ Yes → Proceed
    │  └─ No → 404 Not Found (don't leak info)
    │
    ▼
┌──────────────────────┐
│ AWS IAM Permissions  │
│ (Signed requests)    │
└──────────────────────┘
```

### Encryption Strategy

```
In Transit:
├─ HTTPS (TLS 1.2+)
└─ AWS Signature V4

At Rest:
├─ S3 Server-Side Encryption (SSE-S3)
├─ DynamoDB Encryption
└─ KMS Key Management

Data Access:
├─ IAM Policies
├─ S3 Bucket Policies
├─ Presigned URLs (time-limited)
└─ VPC Endpoints (private access)
```

## Testing Strategy

### Test Pyramid

```
        ▲
       /|\
      / | \
     /  |  \  E2E Tests
    /   |   \─────────────
   /    |    \
  /     |     \  Integration Tests
 /      |      \─────────────
/       |       \
─────────────────  Unit Tests
   (Bottom)
```

### Test Coverage

- **Unit Tests:** 30+ tests
  - Service layer logic
  - AWS client interactions
  - Error handling

- **Integration Tests:** 10+ tests
  - API endpoint behavior
  - Request/response validation
  - Cross-service interactions

- **E2E Tests:** 5+ tests
  - Complete workflows
  - Real AWS services
  - Error recovery

## Deployment Architecture

### Local Development (LocalStack)

```
Machine
├─ Docker Container (LocalStack)
│  ├─ S3 (Port 4566)
│  └─ DynamoDB (Port 4566)
│
└─ Flask App (Port 5000)
   └─ Connects to LocalStack
```

### AWS Production

```
AWS Account
├─ API Gateway (HTTPS)
├─ Lambda Functions (Serverless)
│  └─ Scales automatically
├─ S3 Bucket (Image Storage)
│  └─ Versioning + Encryption
└─ DynamoDB Table (Metadata)
   ├─ On-demand scaling
   └─ Global Secondary Indexes
```

### Deployment Options

1. **Lambda + API Gateway**
   - Serverless, pay-per-request
   - Auto-scaling out of the box
   - Cold start optimization needed

2. **ECS/Fargate + ALB**
   - Container-based, managed by AWS
   - Better for consistent performance
   - More control over infrastructure

3. **EC2 + Auto Scaling Group**
   - Full control, more operational overhead
   - Better for legacy integration
   - Requires manual scaling configuration

## Monitoring & Logging

### Key Metrics

```
API Level:
├─ Request rate (req/sec)
├─ Response time (ms)
├─ Error rate (%)
└─ Status code distribution

AWS Level:
├─ S3: Upload/download speed, success rate
├─ DynamoDB: Consumed capacity, query latency
└─ Lambda: Duration, memory usage, errors
```

### Logging Strategy

```
Python Logging
├─ INFO: Normal operations
├─ WARNING: Recoverable issues
├─ ERROR: Failed operations
└─ DEBUG: Detailed diagnostics

CloudWatch
├─ API logs (requests/responses)
├─ Application logs (business logic)
├─ AWS service logs (S3, DynamoDB)
└─ Alarms (threshold-based)
```

## Future Enhancements

### Short Term
- [ ] Image thumbnails generation
- [ ] Rate limiting and throttling
- [ ] Request signing/validation
- [ ] Batch operations

### Medium Term
- [ ] Full-text search (Elasticsearch)
- [ ] Image recognition (AWS Rekognition)
- [ ] Collaborative features (sharing)
- [ ] Advanced analytics

### Long Term
- [ ] Multi-region replication
- [ ] Machine learning recommendations
- [ ] Real-time notifications (WebSocket)
- [ ] Custom image processing pipelines

---

**For more details, see README.md and TESTING_GUIDE.md**
