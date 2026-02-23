import io
import os
import pytest
import boto3
from unittest.mock import patch
from moto import mock_s3, mock_dynamodb

# Set dummy AWS credentials before any imports so moto works correctly
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_REGION', 'us-east-1')
os.environ.setdefault('S3_BUCKET_NAME', 'test-bucket')
os.environ.setdefault('DYNAMODB_TABLE_NAME', 'test-images-metadata')

from app import app  # noqa: E402

# ── Shared test constants ──────────────────────────────────────────────────────
TEST_USER_ID  = 'test-user-123'
TEST_IMAGE_ID = '550e8400-e29b-41d4-a716-446655440000'
TEST_S3_KEY   = 'images/uuid/test.jpg'

SAMPLE_METADATA = {
    'image_id':    TEST_IMAGE_ID,
    'user_id':     TEST_USER_ID,
    's3_key':      TEST_S3_KEY,
    'title':       'Test Image',
    'description': 'A test image',
    'tags':        ['test', 'sample'],
    'created_at':  '2024-01-01T00:00:00',
    'updated_at':  '2024-01-01T00:00:00',
}


# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    app.config['TESTING'] = True
    if hasattr(app, 'resources_initialized'):
        del app.resources_initialized
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_aws_factory():
    """Reset AWSClientFactory singleton clients between every test."""
    from services import AWSClientFactory
    AWSClientFactory._s3_client        = None
    AWSClientFactory._dynamodb_client  = None
    AWSClientFactory._dynamodb_resource = None
    yield
    AWSClientFactory._s3_client        = None
    AWSClientFactory._dynamodb_client  = None
    AWSClientFactory._dynamodb_resource = None


def make_image_file(filename='test.jpg', content=b'fake image data'):
    return (io.BytesIO(content), filename)


# ── Helper: patch both services with sensible defaults ────────────────────────
def _patch_services(mock_storage, mock_metadata):
    mock_storage.create_bucket_if_not_exists.return_value  = True
    mock_metadata.create_table_if_not_exists.return_value = True


# ══════════════════════════════════════════════════════════════════════════════
# Health Check
# ══════════════════════════════════════════════════════════════════════════════
class TestHealthCheck:
    def test_returns_200_and_healthy(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            response = client.get('/health')
        assert response.status_code == 200
        assert response.get_json() == {'status': 'healthy'}


# ══════════════════════════════════════════════════════════════════════════════
# Upload Image  POST /api/v1/images/upload
# ══════════════════════════════════════════════════════════════════════════════
class TestUploadImage:
    def _setup(self, mock_storage, mock_metadata,
               s3_key=TEST_S3_KEY, save_ok=True):
        _patch_services(mock_storage, mock_metadata)
        mock_storage.upload_image.return_value   = s3_key
        mock_metadata.save_metadata.return_value = save_ok

    def test_upload_success_returns_201(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            data = {
                'file':        make_image_file(),
                'title':       'My Photo',
                'description': 'Nice shot',
                'tags':        'nature,sunset',
            }
            resp = client.post('/api/v1/images/upload',
                               data=data, content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['message']  == 'Image uploaded successfully'
        assert body['user_id']  == TEST_USER_ID
        assert body['title']    == 'My Photo'
        assert body['tags']     == ['nature', 'sunset']
        assert 'image_id' in body

    def test_upload_default_title_when_omitted(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.post('/api/v1/images/upload',
                               data={'file': make_image_file()},
                               content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 201
        assert resp.get_json()['title'] == 'Untitled'

    def test_upload_missing_user_header_returns_401(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.post('/api/v1/images/upload',
                               data={'file': make_image_file()},
                               content_type='multipart/form-data')
        assert resp.status_code == 401

    def test_upload_no_file_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.post('/api/v1/images/upload',
                               data={}, content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400
        assert 'No file provided' in resp.get_json()['error']

    def test_upload_empty_filename_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            data = {'file': (io.BytesIO(b'data'), '')}
            resp = client.post('/api/v1/images/upload',
                               data=data, content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400
        assert 'No file selected' in resp.get_json()['error']

    def test_upload_invalid_type_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.post('/api/v1/images/upload',
                               data={'file': make_image_file('doc.pdf')},
                               content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400
        assert 'File type not allowed' in resp.get_json()['error']

    def test_upload_s3_failure_returns_500(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm, s3_key=None)
            resp = client.post('/api/v1/images/upload',
                               data={'file': make_image_file()},
                               content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500

    def test_upload_metadata_failure_rolls_back_s3(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm, save_ok=False)
            resp = client.post('/api/v1/images/upload',
                               data={'file': make_image_file()},
                               content_type='multipart/form-data',
                               headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500
        ms.delete_image.assert_called_once_with(TEST_S3_KEY)

    def test_upload_all_allowed_extensions(self, client):
        for ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
                self._setup(ms, mm)
                resp = client.post('/api/v1/images/upload',
                                   data={'file': make_image_file(f'img.{ext}')},
                                   content_type='multipart/form-data',
                                   headers={'X-User-ID': TEST_USER_ID})
            assert resp.status_code == 201, f'extension {ext} should be allowed'


# ══════════════════════════════════════════════════════════════════════════════
# List Images  GET /api/v1/images
# ══════════════════════════════════════════════════════════════════════════════
class TestListImages:
    def _setup(self, mock_storage, mock_metadata, images=None):
        _patch_services(mock_storage, mock_metadata)
        mock_storage.generate_presigned_url.return_value     = 'http://presigned'
        mock_metadata.list_images_by_user.return_value       = images if images is not None else [SAMPLE_METADATA.copy()]
        mock_metadata.search_images_by_tags.return_value     = images if images is not None else [SAMPLE_METADATA.copy()]
        mock_metadata.search_images_by_title.return_value    = images if images is not None else [SAMPLE_METADATA.copy()]

    def test_list_by_user_default(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images', headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['filter'] == 'user'
        assert body['count']  == 1

    def test_list_by_user_presigned_url_attached(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images', headers={'X-User-ID': TEST_USER_ID})
        assert resp.get_json()['images'][0]['url'] == 'http://presigned'

    def test_list_by_tags(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images?filter_by=tags&tags=nature',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        assert resp.get_json()['filter'] == 'tags'

    def test_list_by_tags_missing_param_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images?filter_by=tags',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400

    def test_list_by_title(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images?filter_by=title&title=Sunset',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        assert resp.get_json()['filter'] == 'title'

    def test_list_by_title_missing_param_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images?filter_by=title',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400

    def test_list_invalid_filter_returns_400(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images?filter_by=unknown',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 400

    def test_list_missing_header_returns_401(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm)
            resp = client.get('/api/v1/images')
        assert resp.status_code == 401

    def test_list_empty_result(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            self._setup(ms, mm, images=[])
            resp = client.get('/api/v1/images', headers={'X-User-ID': TEST_USER_ID})
        body = resp.get_json()
        assert body['count']  == 0
        assert body['images'] == []


# ══════════════════════════════════════════════════════════════════════════════
# Get Image  GET /api/v1/images/<image_id>
# ══════════════════════════════════════════════════════════════════════════════
class TestGetImage:
    def test_get_image_success_returns_binary(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            ms.get_image.return_value          = b'PNGBYTES'
            resp = client.get(f'/api/v1/images/{TEST_IMAGE_ID}',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        assert resp.data == b'PNGBYTES'

    def test_get_image_not_found_returns_404(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = None
            resp = client.get(f'/api/v1/images/{TEST_IMAGE_ID}',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 404

    def test_get_image_s3_failure_returns_500(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            ms.get_image.return_value          = None
            resp = client.get(f'/api/v1/images/{TEST_IMAGE_ID}',
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500

    def test_get_image_missing_header_returns_401(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.get(f'/api/v1/images/{TEST_IMAGE_ID}')
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Delete Image  DELETE /api/v1/images/<image_id>
# ══════════════════════════════════════════════════════════════════════════════
class TestDeleteImage:
    def test_delete_success_returns_200(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            ms.delete_image.return_value       = True
            mm.delete_metadata.return_value    = True
            resp = client.delete(f'/api/v1/images/{TEST_IMAGE_ID}',
                                 headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'Image deleted successfully'

    def test_delete_not_found_returns_404(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = None
            resp = client.delete(f'/api/v1/images/{TEST_IMAGE_ID}',
                                 headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 404

    def test_delete_s3_failure_returns_500(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            ms.delete_image.return_value       = False
            resp = client.delete(f'/api/v1/images/{TEST_IMAGE_ID}',
                                 headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500

    def test_delete_metadata_failure_returns_500(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            ms.delete_image.return_value       = True
            mm.delete_metadata.return_value    = False
            resp = client.delete(f'/api/v1/images/{TEST_IMAGE_ID}',
                                 headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500

    def test_delete_missing_header_returns_401(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.delete(f'/api/v1/images/{TEST_IMAGE_ID}')
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Update Metadata  PUT /api/v1/images/<image_id>
# ══════════════════════════════════════════════════════════════════════════════
class TestUpdateImageMetadata:
    def test_update_success_returns_200(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            mm.update_metadata.return_value    = True
            resp = client.put(f'/api/v1/images/{TEST_IMAGE_ID}',
                              json={'title': 'New Title', 'description': 'New', 'tags': ['x']},
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'Metadata updated successfully'

    def test_update_not_found_returns_404(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = None
            resp = client.put(f'/api/v1/images/{TEST_IMAGE_ID}',
                              json={'title': 'X'},
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 404

    def test_update_service_failure_returns_500(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            mm.update_metadata.return_value    = False
            resp = client.put(f'/api/v1/images/{TEST_IMAGE_ID}',
                              json={'title': 'X'},
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 500

    def test_update_partial_fields_accepted(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            mm.get_image_metadata.return_value = SAMPLE_METADATA
            mm.update_metadata.return_value    = True
            resp = client.put(f'/api/v1/images/{TEST_IMAGE_ID}',
                              json={'title': 'Only Title Updated'},
                              headers={'X-User-ID': TEST_USER_ID})
        assert resp.status_code == 200

    def test_update_missing_header_returns_401(self, client):
        with patch('app.storage_service') as ms, patch('app.metadata_service') as mm:
            _patch_services(ms, mm)
            resp = client.put(f'/api/v1/images/{TEST_IMAGE_ID}',
                              json={'title': 'X'})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# ImageStorageService  (moto S3)
# ══════════════════════════════════════════════════════════════════════════════
class TestImageStorageService:
    def _make_service(self, bucket='test-bucket'):
        from services import AWSClientFactory, ImageStorageService
        AWSClientFactory._s3_client = None
        return ImageStorageService(bucket)

    def _create_bucket(self, bucket='test-bucket'):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=bucket)
        return s3

    @mock_s3
    def test_create_bucket_returns_true(self):
        service = self._make_service()
        assert service.create_bucket_if_not_exists() is True

    @mock_s3
    def test_create_bucket_already_exists_returns_true(self):
        self._create_bucket()
        service = self._make_service()
        assert service.create_bucket_if_not_exists() is True

    @mock_s3
    def test_upload_image_returns_s3_key(self):
        self._create_bucket()
        service = self._make_service()
        key = service.upload_image(b'image bytes', 'photo.jpg')
        assert key is not None
        assert 'photo.jpg' in key

    @mock_s3
    def test_upload_image_stores_retrievable_data(self):
        self._create_bucket()
        service = self._make_service()
        key = service.upload_image(b'hello world', 'test.jpg')
        data = service.get_image(key)
        assert data == b'hello world'

    @mock_s3
    def test_get_image_not_found_returns_none(self):
        self._create_bucket()
        service = self._make_service()
        assert service.get_image('no/such/key.jpg') is None

    @mock_s3
    def test_delete_image_returns_true(self):
        s3 = self._create_bucket()
        s3.put_object(Bucket='test-bucket', Key='images/del.jpg', Body=b'data')
        service = self._make_service()
        assert service.delete_image('images/del.jpg') is True

    @mock_s3
    def test_generate_presigned_url_contains_bucket(self):
        s3 = self._create_bucket()
        s3.put_object(Bucket='test-bucket', Key='images/pic.jpg', Body=b'data')
        service = self._make_service()
        url = service.generate_presigned_url('images/pic.jpg')
        assert url is not None
        assert 'test-bucket' in url


# ══════════════════════════════════════════════════════════════════════════════
# ImageMetadataService  (moto DynamoDB)
# ══════════════════════════════════════════════════════════════════════════════
class TestImageMetadataService:
    def _make_service(self, table='test-table'):
        from services import AWSClientFactory, ImageMetadataService
        AWSClientFactory._dynamodb_client   = None
        AWSClientFactory._dynamodb_resource = None
        svc = ImageMetadataService(table)
        svc.create_table_if_not_exists()
        return svc

    @mock_dynamodb
    def test_create_table_returns_true(self):
        from services import AWSClientFactory, ImageMetadataService
        AWSClientFactory._dynamodb_client   = None
        AWSClientFactory._dynamodb_resource = None
        svc = ImageMetadataService('test-table')
        assert svc.create_table_if_not_exists() is True

    @mock_dynamodb
    def test_save_and_get_metadata(self):
        svc = self._make_service()
        ok = svc.save_metadata('user1', 'img1', 'images/img1.jpg',
                               'Title', 'Desc', ['a', 'b'])
        assert ok is True
        item = svc.get_image_metadata('img1', 'user1')
        assert item is not None
        assert item['title']   == 'Title'
        assert item['user_id'] == 'user1'
        assert item['tags']    == ['a', 'b']

    @mock_dynamodb
    def test_get_metadata_not_found_returns_none(self):
        svc = self._make_service()
        assert svc.get_image_metadata('ghost', 'user1') is None

    @mock_dynamodb
    def test_list_images_by_user(self):
        svc = self._make_service()
        svc.save_metadata('user1', 'img1', 'images/img1.jpg', 'T1', 'D', ['x'])
        svc.save_metadata('user1', 'img2', 'images/img2.jpg', 'T2', 'D', ['y'])
        svc.save_metadata('user2', 'img3', 'images/img3.jpg', 'T3', 'D', ['z'])
        items = svc.list_images_by_user('user1', limit=10)
        assert len(items) == 2
        assert all(i['user_id'] == 'user1' for i in items)

    @mock_dynamodb
    def test_list_images_by_user_empty(self):
        svc = self._make_service()
        assert svc.list_images_by_user('nobody', limit=10) == []

    @mock_dynamodb
    def test_search_by_title(self):
        svc = self._make_service()
        svc.save_metadata('user1', 'img1', 'images/img1.jpg', 'Sunset', 'D', [])
        svc.save_metadata('user1', 'img2', 'images/img2.jpg', 'Mountains', 'D', [])
        items = svc.search_images_by_title('Sunset', limit=10)
        assert len(items) == 1
        assert items[0]['title'] == 'Sunset'

    @mock_dynamodb
    def test_search_by_tags(self):
        svc = self._make_service()
        svc.save_metadata('user1', 'img1', 'images/img1.jpg', 'T1', 'D', ['nature', 'sunset'])
        svc.save_metadata('user1', 'img2', 'images/img2.jpg', 'T2', 'D', ['city'])
        items = svc.search_images_by_tags('user1', ['nature'], limit=10)
        assert len(items) == 1
        assert 'nature' in items[0]['tags']

    @mock_dynamodb
    def test_update_metadata_title_and_tags(self):
        svc = self._make_service()
        svc.save_metadata('user1', 'img1', 'images/img1.jpg', 'Old', 'OldDesc', ['old'])
        ok = svc.update_metadata('img1', 'user1',
                                 title='New', description='NewDesc', tags=['new'])
        assert ok is True
        item = svc.get_image_metadata('img1', 'user1')
        assert item['title']       == 'New'
        assert item['description'] == 'NewDesc'
        assert 'new' in item['tags']

    @mock_dynamodb
    def test_delete_metadata(self):
        svc = self._make_service()
        svc.save_metadata('user1', 'img1', 'images/img1.jpg', 'T', 'D', [])
        assert svc.delete_metadata('img1', 'user1') is True
        assert svc.get_image_metadata('img1', 'user1') is None

    @mock_dynamodb
    def test_list_respects_limit(self):
        svc = self._make_service()
        for i in range(5):
            svc.save_metadata('user1', f'img{i}', f'images/img{i}.jpg',
                              f'Title{i}', 'D', [])
        items = svc.list_images_by_user('user1', limit=3)
        assert len(items) <= 3
