import pytest
import json
import os
from io import BytesIO
from unittest.mock import patch, MagicMock
from app import app, storage_service, metadata_service
from services import ImageStorageService, ImageMetadataService, AWSClientFactory
from config import S3_BUCKET_NAME, DYNAMODB_TABLE_NAME


@pytest.fixture
def client():
    """Create Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_image():
    """Create a sample image file for testing"""
    return BytesIO(b'fake image data').getvalue()


@pytest.fixture
def user_id():
    """Sample user ID"""
    return 'test-user-123'


@pytest.fixture
def mock_s3():
    """Mock S3 operations"""
    with patch('services.AWSClientFactory.get_s3_client') as mock:
        yield mock.return_value


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB operations"""
    with patch('services.AWSClientFactory.get_dynamodb_resource') as mock:
        yield mock.return_value


# ============ Upload Image Tests ============

class TestUploadImage:
    
    def test_upload_image_missing_header(self, client):
        """Test upload without X-User-ID header"""
        response = client.post('/api/v1/images/upload')
        assert response.status_code == 401
        assert 'X-User-ID' in response.json['error']
    
    def test_upload_image_no_file(self, client, user_id):
        """Test upload without file"""
        response = client.post(
            '/api/v1/images/upload',
            headers={'X-User-ID': user_id}
        )
        assert response.status_code == 400
        assert 'No file' in response.json['error']
    
    def test_upload_image_invalid_file_type(self, client, user_id):
        """Test upload with invalid file type"""
        data = {
            'file': (BytesIO(b'test'), 'test.txt')
        }
        response = client.post(
            '/api/v1/images/upload',
            data=data,
            headers={'X-User-ID': user_id}
        )
        assert response.status_code == 400
        assert 'not allowed' in response.json['error']
    
    @patch('app.storage_service.upload_image')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    @patch('app.metadata_service.save_metadata')
    def test_upload_image_success(self, mock_save, mock_create_table, mock_create_bucket, 
                                   mock_upload, client, user_id, sample_image):
        """Test successful image upload"""
        mock_upload.return_value = 'images/uuid/test.jpg'
        mock_save.return_value = True
        
        data = {
            'file': (BytesIO(sample_image), 'test.jpg'),
            'title': 'Test Image',
            'description': 'Test Description',
            'tags': 'tag1, tag2'
        }
        
        response = client.post(
            '/api/v1/images/upload',
            data=data,
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 201
        assert response.json['image_id']
        assert response.json['title'] == 'Test Image'
        assert response.json['tags'] == ['tag1', 'tag2']
        mock_save.assert_called_once()
    
    @patch('app.storage_service.upload_image')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    @patch('app.metadata_service.save_metadata')
    def test_upload_image_metadata_failure(self, mock_save, mock_create_table, 
                                           mock_create_bucket, mock_upload, client, user_id, sample_image):
        """Test upload with metadata save failure"""
        mock_upload.return_value = 'images/uuid/test.jpg'
        mock_save.return_value = False
        
        data = {
            'file': (BytesIO(sample_image), 'test.jpg'),
            'title': 'Test Image'
        }
        
        response = client.post(
            '/api/v1/images/upload',
            data=data,
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 500
        assert 'Failed to save' in response.json['error']


# ============ List Images Tests ============

class TestListImages:
    
    def test_list_images_missing_header(self, client):
        """Test list without X-User-ID header"""
        response = client.get('/api/v1/images')
        assert response.status_code == 401
    
    @patch('app.storage_service.generate_presigned_url')
    @patch('app.metadata_service.list_images_by_user')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_list_images_by_user(self, mock_create_table, mock_create_bucket, 
                                  mock_list, mock_url, client, user_id):
        """Test listing images by user"""
        mock_images = [
            {
                'image_id': 'img1',
                'user_id': user_id,
                'title': 'Image 1',
                's3_key': 'images/uuid/img1.jpg'
            }
        ]
        mock_list.return_value = mock_images
        mock_url.return_value = 'http://presigned-url'
        
        response = client.get(
            '/api/v1/images?filter_by=user',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200
        assert response.json['count'] == 1
        assert response.json['images'][0]['url'] == 'http://presigned-url'
    
    @patch('app.metadata_service.search_images_by_tags')
    @patch('app.storage_service.generate_presigned_url')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_list_images_by_tags(self, mock_create_table, mock_create_bucket, 
                                  mock_url, mock_search, client, user_id):
        """Test listing images by tags"""
        mock_images = [
            {
                'image_id': 'img1',
                'tags': ['tag1', 'tag2'],
                's3_key': 'images/uuid/img1.jpg'
            }
        ]
        mock_search.return_value = mock_images
        mock_url.return_value = 'http://presigned-url'
        
        response = client.get(
            '/api/v1/images?filter_by=tags&tags=tag1,tag2',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200
        assert response.json['filter'] == 'tags'
    
    @patch('app.metadata_service.search_images_by_title')
    @patch('app.storage_service.generate_presigned_url')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_list_images_by_title(self, mock_create_table, mock_create_bucket, 
                                   mock_url, mock_search, client, user_id):
        """Test listing images by title"""
        mock_images = [
            {
                'image_id': 'img1',
                'title': 'Test',
                's3_key': 'images/uuid/img1.jpg'
            }
        ]
        mock_search.return_value = mock_images
        mock_url.return_value = 'http://presigned-url'
        
        response = client.get(
            '/api/v1/images?filter_by=title&title=Test',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200
        assert response.json['filter'] == 'title'
    
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_list_images_invalid_filter(self, mock_create_table, mock_create_bucket, client, user_id):
        """Test listing with invalid filter"""
        response = client.get(
            '/api/v1/images?filter_by=invalid',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 400
        assert 'Invalid filter_by' in response.json['error']


# ============ Get Image Tests ============

class TestGetImage:
    
    def test_get_image_missing_header(self, client):
        """Test get without X-User-ID header"""
        response = client.get('/api/v1/images/img1')
        assert response.status_code == 401
    
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_get_image_not_found(self, mock_create_table, mock_create_bucket, 
                                  mock_metadata, client, user_id):
        """Test get non-existent image"""
        mock_metadata.return_value = None
        
        response = client.get(
            '/api/v1/images/img1',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 404
        assert 'not found' in response.json['error']
    
    @patch('app.storage_service.get_image')
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_get_image_success(self, mock_create_table, mock_create_bucket, 
                                mock_metadata, mock_get, client, user_id):
        """Test successful image retrieval"""
        mock_metadata.return_value = {
            'image_id': 'img1',
            'title': 'Test Image',
            's3_key': 'images/uuid/test.jpg'
        }
        mock_get.return_value = b'fake image data'
        
        response = client.get(
            '/api/v1/images/img1',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200


# ============ Delete Image Tests ============

class TestDeleteImage:
    
    def test_delete_image_missing_header(self, client):
        """Test delete without X-User-ID header"""
        response = client.delete('/api/v1/images/img1')
        assert response.status_code == 401
    
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_delete_image_not_found(self, mock_create_table, mock_create_bucket, 
                                     mock_metadata, client, user_id):
        """Test delete non-existent image"""
        mock_metadata.return_value = None
        
        response = client.delete(
            '/api/v1/images/img1',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 404
    
    @patch('app.metadata_service.delete_metadata')
    @patch('app.storage_service.delete_image')
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_delete_image_success(self, mock_create_table, mock_create_bucket, 
                                   mock_metadata, mock_delete_storage, mock_delete_meta, 
                                   client, user_id):
        """Test successful image deletion"""
        mock_metadata.return_value = {
            'image_id': 'img1',
            's3_key': 'images/uuid/test.jpg'
        }
        mock_delete_storage.return_value = True
        mock_delete_meta.return_value = True
        
        response = client.delete(
            '/api/v1/images/img1',
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200
        assert 'deleted successfully' in response.json['message']


# ============ Update Image Metadata Tests ============

class TestUpdateImageMetadata:
    
    def test_update_image_missing_header(self, client):
        """Test update without X-User-ID header"""
        response = client.put('/api/v1/images/img1', json={})
        assert response.status_code == 401
    
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_update_image_not_found(self, mock_create_table, mock_create_bucket, 
                                     mock_metadata, client, user_id):
        """Test update non-existent image"""
        mock_metadata.return_value = None
        
        response = client.put(
            '/api/v1/images/img1',
            json={'title': 'Updated'},
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 404
    
    @patch('app.metadata_service.update_metadata')
    @patch('app.metadata_service.get_image_metadata')
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_update_image_success(self, mock_create_table, mock_create_bucket, 
                                   mock_metadata, mock_update, client, user_id):
        """Test successful metadata update"""
        mock_metadata.return_value = {'image_id': 'img1'}
        mock_update.return_value = True
        
        response = client.put(
            '/api/v1/images/img1',
            json={
                'title': 'Updated Title',
                'description': 'Updated Description',
                'tags': ['tag1', 'tag2']
            },
            headers={'X-User-ID': user_id}
        )
        
        assert response.status_code == 200
        assert 'updated successfully' in response.json['message']


# ============ Health Check Tests ============

class TestHealthCheck:
    
    @patch('app.storage_service.create_bucket_if_not_exists')
    @patch('app.metadata_service.create_table_if_not_exists')
    def test_health_check(self, mock_create_table, mock_create_bucket, client):
        """Test health check endpoint"""
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json['status'] == 'healthy'


# ============ Service Layer Tests ============

class TestImageStorageService:
    
    @patch('services.AWSClientFactory.get_s3_client')
    def test_upload_image(self, mock_s3):
        """Test S3 image upload"""
        mock_client = MagicMock()
        mock_s3.return_value = mock_client
        
        service = ImageStorageService('test-bucket')
        service.s3_client = mock_client
        
        result = service.upload_image(b'test data', 'test.jpg')
        
        assert result is not None
        assert 'test.jpg' in result
        mock_client.put_object.assert_called_once()
    
    @patch('services.AWSClientFactory.get_s3_client')
    def test_delete_image(self, mock_s3):
        """Test S3 image deletion"""
        mock_client = MagicMock()
        mock_s3.return_value = mock_client
        
        service = ImageStorageService('test-bucket')
        service.s3_client = mock_client
        
        result = service.delete_image('images/uuid/test.jpg')
        
        assert result is True
        mock_client.delete_object.assert_called_once()


class TestImageMetadataService:
    
    @patch('services.AWSClientFactory.get_dynamodb_resource')
    def test_save_metadata(self, mock_dynamodb):
        """Test DynamoDB metadata save"""
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        service = ImageMetadataService('test-table')
        service.dynamodb = mock_resource
        
        result = service.save_metadata(
            'user1', 'img1', 'images/uuid/test.jpg',
            'Test', 'Description', ['tag1']
        )
        
        assert result is True
        mock_table.put_item.assert_called_once()
    
    @patch('services.AWSClientFactory.get_dynamodb_resource')
    def test_get_metadata(self, mock_dynamodb):
        """Test DynamoDB metadata retrieval"""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'image_id': 'img1', 'title': 'Test'}
        }
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource
        
        service = ImageMetadataService('test-table')
        service.dynamodb = mock_resource
        
        result = service.get_image_metadata('img1', 'user1')
        
        assert result is not None
        assert result['image_id'] == 'img1'
