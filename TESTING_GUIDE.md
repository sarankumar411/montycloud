# API Testing Guide

This document provides examples of how to test the Image Upload Service API using various tools.

## Table of Contents

1. [cURL Examples](#curl-examples)
2. [Python Requests Examples](#python-requests-examples)
3. [Postman Collection](#postman-collection)
4. [Integration Test Script](#integration-test-script)

---

## cURL Examples

### Prerequisites

Ensure the API is running:
```bash
python app.py
```

And LocalStack is running:
```bash
docker-compose up -d
```

### 1. Health Check

```bash
curl -X GET http://localhost:5000/health
```

### 2. Upload Image

#### Basic upload with just file:
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user-123" \
  -F "file=@./sample.jpg"
```

#### Upload with full metadata:
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user-123" \
  -F "file=@./sample.jpg" \
  -F "title=My Vacation Photo" \
  -F "description=Beautiful sunset at the beach" \
  -F "tags=vacation, beach, sunset, 2024"
```

**Save response for later use:**
```bash
curl -X POST http://localhost:5000/api/v1/images/upload \
  -H "X-User-ID: user-123" \
  -F "file=@./sample.jpg" \
  -F "title=Test Image" | jq .
```

### 3. List Images

#### List user's own images:
```bash
curl -X GET "http://localhost:5000/api/v1/images" \
  -H "X-User-ID: user-123"
```

#### List with limit:
```bash
curl -X GET "http://localhost:5000/api/v1/images?limit=5" \
  -H "X-User-ID: user-123"
```

#### Search by tags:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=tags&tags=vacation,beach" \
  -H "X-User-ID: user-123"
```

#### Search by title:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=title&title=Vacation" \
  -H "X-User-ID: user-123"
```

#### List another user's images:
```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=user&user_id=user-456&limit=10" \
  -H "X-User-ID: user-123"
```

### 4. Get Image Details (with metadata)

```bash
curl -X GET "http://localhost:5000/api/v1/images?filter_by=user" \
  -H "X-User-ID: user-123" | jq '.images[0]'
```

Extract image_id from response and use it.

### 5. Download Image

```bash
curl -X GET "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123" \
  -o downloaded_image.jpg
```

### 6. Update Image Metadata

```bash
curl -X PUT "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Vacation Photo",
    "description": "Updated description",
    "tags": ["updated", "vacation", "beach"]
  }'
```

### 7. Delete Image

```bash
curl -X DELETE "http://localhost:5000/api/v1/images/550e8400-e29b-41d4-a716-446655440000" \
  -H "X-User-ID: user-123"
```

---

## Python Requests Examples

Create a file `test_api.py`:

```python
import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:5000/api/v1"
HEADERS = {"X-User-ID": "user-123"}

class ImageAPIClient:
    def __init__(self, base_url=BASE_URL, user_id="user-123"):
        self.base_url = base_url
        self.headers = {"X-User-ID": user_id}
    
    def upload_image(self, file_path, title=None, description=None, tags=None):
        """Upload image with optional metadata"""
        url = f"{self.base_url}/images/upload"
        
        with open(file_path, 'rb') as f:
            files = {'file': (Path(file_path).name, f)}
            data = {}
            if title:
                data['title'] = title
            if description:
                data['description'] = description
            if tags:
                data['tags'] = ','.join(tags) if isinstance(tags, list) else tags
            
            response = requests.post(url, headers=self.headers, files=files, data=data)
            return response.json(), response.status_code
    
    def list_images(self, filter_by='user', user_id=None, tags=None, title=None, limit=10):
        """List images with filters"""
        url = f"{self.base_url}/images"
        params = {
            'filter_by': filter_by,
            'limit': limit
        }
        
        if filter_by == 'user' and user_id:
            params['user_id'] = user_id
        elif filter_by == 'tags' and tags:
            params['tags'] = ','.join(tags) if isinstance(tags, list) else tags
        elif filter_by == 'title' and title:
            params['title'] = title
        
        response = requests.get(url, headers=self.headers, params=params)
        return response.json(), response.status_code
    
    def get_image(self, image_id):
        """Download image"""
        url = f"{self.base_url}/images/{image_id}"
        response = requests.get(url, headers=self.headers)
        return response.content, response.status_code
    
    def delete_image(self, image_id):
        """Delete image"""
        url = f"{self.base_url}/images/{image_id}"
        response = requests.delete(url, headers=self.headers)
        return response.json(), response.status_code
    
    def update_image(self, image_id, title=None, description=None, tags=None):
        """Update image metadata"""
        url = f"{self.base_url}/images/{image_id}"
        payload = {}
        if title:
            payload['title'] = title
        if description:
            payload['description'] = description
        if tags:
            payload['tags'] = tags if isinstance(tags, list) else tags.split(',')
        
        response = requests.put(url, headers=self.headers, json=payload)
        return response.json(), response.status_code


# Usage Examples
if __name__ == "__main__":
    client = ImageAPIClient()
    
    # Upload image
    print("=== Upload Image ===")
    result, status = client.upload_image(
        './sample.jpg',
        title='My Beach Photo',
        description='Beautiful sunset',
        tags=['vacation', 'beach', 'sunset']
    )
    print(f"Status: {status}")
    print(f"Result: {json.dumps(result, indent=2)}")
    
    image_id = result['image_id']
    
    # List user's images
    print("\n=== List User Images ===")
    result, status = client.list_images(filter_by='user', limit=5)
    print(f"Status: {status}")
    print(f"Found {result['count']} images")
    
    # Search by tags
    print("\n=== Search by Tags ===")
    result, status = client.list_images(filter_by='tags', tags=['vacation'])
    print(f"Status: {status}")
    print(f"Found {result['count']} images with tag 'vacation'")
    
    # Update image
    print("\n=== Update Image ===")
    result, status = client.update_image(
        image_id,
        title='Updated Beach Photo',
        tags=['updated', 'vacation', 'beach']
    )
    print(f"Status: {status}")
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Delete image
    print("\n=== Delete Image ===")
    result, status = client.delete_image(image_id)
    print(f"Status: {status}")
    print(f"Result: {json.dumps(result, indent=2)}")
```

Run the test:
```bash
python test_api.py
```

---

## Postman Collection

Create a file `Image_API.postman_collection.json`:

```json
{
  "info": {
    "name": "Image Upload Service API",
    "description": "API collection for Instagram-like image upload service",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "http://localhost:5000/health",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["health"]
        }
      }
    },
    {
      "name": "Upload Image",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          }
        ],
        "body": {
          "mode": "formdata",
          "formdata": [
            {
              "key": "file",
              "type": "file",
              "src": "sample.jpg"
            },
            {
              "key": "title",
              "value": "My Vacation Photo",
              "type": "text"
            },
            {
              "key": "description",
              "value": "Beautiful beach sunset",
              "type": "text"
            },
            {
              "key": "tags",
              "value": "vacation, beach, sunset",
              "type": "text"
            }
          ]
        },
        "url": {
          "raw": "http://localhost:5000/api/v1/images/upload",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images", "upload"]
        }
      }
    },
    {
      "name": "List Images",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          }
        ],
        "url": {
          "raw": "http://localhost:5000/api/v1/images?filter_by=user&limit=10",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images"],
          "query": [
            {
              "key": "filter_by",
              "value": "user"
            },
            {
              "key": "limit",
              "value": "10"
            }
          ]
        }
      }
    },
    {
      "name": "Search by Tags",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          }
        ],
        "url": {
          "raw": "http://localhost:5000/api/v1/images?filter_by=tags&tags=vacation,beach&limit=10",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images"],
          "query": [
            {
              "key": "filter_by",
              "value": "tags"
            },
            {
              "key": "tags",
              "value": "vacation,beach"
            },
            {
              "key": "limit",
              "value": "10"
            }
          ]
        }
      }
    },
    {
      "name": "Download Image",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          }
        ],
        "url": {
          "raw": "http://localhost:5000/api/v1/images/{{image_id}}",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images", "{{image_id}}"]
        }
      }
    },
    {
      "name": "Update Image",
      "request": {
        "method": "PUT",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          },
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"title\": \"Updated Title\",\n  \"description\": \"Updated description\",\n  \"tags\": [\"updated\", \"vacation\"]\n}"
        },
        "url": {
          "raw": "http://localhost:5000/api/v1/images/{{image_id}}",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images", "{{image_id}}"]
        }
      }
    },
    {
      "name": "Delete Image",
      "request": {
        "method": "DELETE",
        "header": [
          {
            "key": "X-User-ID",
            "value": "user-123"
          }
        ],
        "url": {
          "raw": "http://localhost:5000/api/v1/images/{{image_id}}",
          "protocol": "http",
          "host": ["localhost"],
          "port": "5000",
          "path": ["api", "v1", "images", "{{image_id}}"]
        }
      }
    }
  ],
  "variable": [
    {
      "key": "image_id",
      "value": "550e8400-e29b-41d4-a716-446655440000"
    }
  ]
}
```

Import into Postman: File → Import → select this file

---

## Integration Test Script

Create a file `integration_test.py`:

```python
#!/usr/bin/env python3
"""
Integration test script for Image Upload Service
Tests all API endpoints in a realistic workflow
"""

import requests
import time
import json
from pathlib import Path
from PIL import Image
import io

BASE_URL = "http://localhost:5000/api/v1"

def create_test_image(width=100, height=100, filename="test_image.jpg"):
    """Create a test image file"""
    img = Image.new('RGB', (width, height), color='red')
    img.save(filename)
    return filename

def test_workflow():
    """Run a complete workflow test"""
    print("=" * 60)
    print("Image Upload Service - Integration Test")
    print("=" * 60)
    
    # Setup
    user_id = "test-user-" + str(int(time.time()))
    headers = {"X-User-ID": user_id}
    image_ids = []
    
    print(f"\nTest User ID: {user_id}")
    
    # Create test image
    print("\n[1/6] Creating test image...")
    image_file = create_test_image()
    print(f"✓ Created {image_file}")
    
    # Upload multiple images
    print("\n[2/6] Uploading images...")
    for i in range(3):
        with open(image_file, 'rb') as f:
            files = {'file': f}
            data = {
                'title': f'Test Image {i+1}',
                'description': f'Test description {i+1}',
                'tags': f'test, image-{i+1}' if i == 0 else f'test, vacation' if i == 1 else 'test, work'
            }
            
            response = requests.post(
                f"{BASE_URL}/images/upload",
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code == 201:
                result = response.json()
                image_ids.append(result['image_id'])
                print(f"✓ Uploaded image {i+1}: {result['image_id']}")
            else:
                print(f"✗ Upload failed: {response.json()}")
                return False
    
    # List images
    print("\n[3/6] Listing images...")
    response = requests.get(
        f"{BASE_URL}/images",
        headers=headers,
        params={'filter_by': 'user', 'limit': 10}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Found {result['count']} images")
    else:
        print(f"✗ List failed: {response.json()}")
        return False
    
    # Search by tags
    print("\n[4/6] Searching by tags...")
    response = requests.get(
        f"{BASE_URL}/images",
        headers=headers,
        params={'filter_by': 'tags', 'tags': 'vacation', 'limit': 10}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Found {result['count']} images with 'vacation' tag")
    else:
        print(f"✗ Search failed: {response.json()}")
        return False
    
    # Update image
    print("\n[5/6] Updating image metadata...")
    response = requests.put(
        f"{BASE_URL}/images/{image_ids[0]}",
        headers=headers,
        json={
            'title': 'Updated Title',
            'tags': ['updated', 'test']
        }
    )
    
    if response.status_code == 200:
        print(f"✓ Updated image {image_ids[0]}")
    else:
        print(f"✗ Update failed: {response.json()}")
        return False
    
    # Delete image
    print("\n[6/6] Deleting image...")
    response = requests.delete(
        f"{BASE_URL}/images/{image_ids[0]}",
        headers=headers
    )
    
    if response.status_code == 200:
        print(f"✓ Deleted image {image_ids[0]}")
    else:
        print(f"✗ Delete failed: {response.json()}")
        return False
    
    # Cleanup
    Path(image_file).unlink()
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_workflow()
    exit(0 if success else 1)
```

Run the integration test:
```bash
python integration_test.py
```

---

## Performance Testing

Use Apache Bench to test concurrent uploads:

```bash
# Single request
ab -n 1 -c 1 http://localhost:5000/health

# 100 concurrent requests
ab -n 100 -c 10 http://localhost:5000/health
```

Or use `wrk` for more detailed performance metrics:

```bash
wrk -t4 -c100 -d30s http://localhost:5000/health
```

---

## Troubleshooting Test Issues

### Connection Refused
```bash
# Check if API is running
curl http://localhost:5000/health

# Check if LocalStack is running
docker-compose ps
```

### File Not Found
```bash
# Create a test image first
python -c "from PIL import Image; Image.new('RGB', (100, 100), 'red').save('sample.jpg')"
```

### Missing Dependencies
```bash
pip install -r requirements.txt
```
