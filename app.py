from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import logging
from config import (
    S3_BUCKET_NAME, DYNAMODB_TABLE_NAME, MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS, DEBUG
)
from services import ImageStorageService, ImageMetadataService
import uuid
from functools import wraps
from io import BytesIO
from flasgger import Swagger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/swagger/",
}

swagger_template = {
    "info": {
        "title": "Image Upload Service API",
        "description": "Instagram-like image upload service backed by AWS S3 and DynamoDB",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "UserID": {
            "type": "apiKey",
            "in": "header",
            "name": "X-User-ID",
            "description": "User identifier header required for all endpoints"
        }
    },
    "security": [{"UserID": []}],
    "consumes": ["application/json", "multipart/form-data"],
    "produces": ["application/json"],
}

Swagger(app, config=swagger_config, template=swagger_template)

# Initialize services
storage_service = ImageStorageService(S3_BUCKET_NAME)
metadata_service = ImageMetadataService(DYNAMODB_TABLE_NAME)


def validate_request():
    """Decorator to validate common request parameters"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = request.headers.get('X-User-ID')
            if not user_id:
                return jsonify({'error': 'X-User-ID header is required'}), 401
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.before_request
def initialize_aws_resources():
    """Initialize AWS resources on first request"""
    if not hasattr(app, 'resources_initialized'):
        storage_service.create_bucket_if_not_exists()
        metadata_service.create_table_if_not_exists()
        app.resources_initialized = True


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    ---
    tags:
      - Health
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
    """
    return jsonify({'status': 'healthy'}), 200


@app.route('/api/v1/images/upload', methods=['POST'])
@validate_request()
def upload_image():
    """
    Upload an image with metadata
    ---
    tags:
      - Images
    consumes:
      - multipart/form-data
    parameters:
      - name: X-User-ID
        in: header
        required: true
        type: string
        description: User identifier
      - name: file
        in: formData
        required: true
        type: file
        description: Image file (jpg, jpeg, png, gif, webp - max 10MB)
      - name: title
        in: formData
        required: false
        type: string
        description: Image title
      - name: description
        in: formData
        required: false
        type: string
        description: Image description
      - name: tags
        in: formData
        required: false
        type: string
        description: Comma-separated tags (e.g. nature,sunset,beach)
    responses:
      201:
        description: Image uploaded successfully
      400:
        description: Bad request - missing file or invalid format
      401:
        description: Missing X-User-ID header
      413:
        description: File too large (max 10MB)
      500:
        description: Internal server error
    """
    try:
        user_id = request.headers.get('X-User-ID')
        
        # Validate file presence
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        # Read file data
        file_data = file.read()
        if len(file_data) > MAX_FILE_SIZE:
            return jsonify({'error': f'File too large. Max size: {MAX_FILE_SIZE / (1024*1024)}MB'}), 413
        
        # Upload to S3
        filename = secure_filename(file.filename)
        s3_key = storage_service.upload_image(file_data, filename)
        
        if not s3_key:
            return jsonify({'error': 'Failed to upload image to storage'}), 500
        
        # Save metadata to DynamoDB
        image_id = str(uuid.uuid4())
        title = request.form.get('title', 'Untitled')
        description = request.form.get('description', '')
        tags = [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()]
        
        if not metadata_service.save_metadata(user_id, image_id, s3_key, title, description, tags):
            # Rollback: delete image from S3
            storage_service.delete_image(s3_key)
            return jsonify({'error': 'Failed to save image metadata'}), 500
        
        return jsonify({
            'message': 'Image uploaded successfully',
            'image_id': image_id,
            'user_id': user_id,
            's3_key': s3_key,
            'title': title,
            'description': description,
            'tags': tags
        }), 201
    
    except Exception as e:
        logger.error(f"Error uploading image: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/v1/images', methods=['GET'])
@validate_request()
def list_images():
    """
    List images with optional filters
    ---
    tags:
      - Images
    parameters:
      - name: X-User-ID
        in: header
        required: true
        type: string
        description: User identifier
      - name: filter_by
        in: query
        required: false
        type: string
        enum: [user, tags, title]
        default: user
        description: Filter type
      - name: user_id
        in: query
        required: false
        type: string
        description: User ID to filter by (used when filter_by=user)
      - name: tags
        in: query
        required: false
        type: string
        description: Comma-separated tags (used when filter_by=tags)
      - name: title
        in: query
        required: false
        type: string
        description: Title to search (used when filter_by=title)
      - name: limit
        in: query
        required: false
        type: integer
        default: 10
        maximum: 100
        description: Number of results to return
    responses:
      200:
        description: List of images
      400:
        description: Invalid parameters
      401:
        description: Missing X-User-ID header
      500:
        description: Internal server error
    """
    try:
        user_id = request.headers.get('X-User-ID')
        filter_by = request.args.get('filter_by', 'user').lower()
        limit = min(int(request.args.get('limit', 10)), 100)
        
        images = []
        
        if filter_by == 'user':
            target_user_id = request.args.get('user_id', user_id)
            images = metadata_service.list_images_by_user(target_user_id, limit)
        
        elif filter_by == 'tags':
            tags = request.args.get('tags', '')
            if not tags:
                return jsonify({'error': 'tags parameter required for tags filter'}), 400
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            images = metadata_service.search_images_by_tags(user_id, tag_list, limit)
        
        elif filter_by == 'title':
            title = request.args.get('title', '')
            if not title:
                return jsonify({'error': 'title parameter required for title filter'}), 400
            images = metadata_service.search_images_by_title(title, limit)
        
        else:
            return jsonify({'error': 'Invalid filter_by parameter. Valid values: user, tags, title'}), 400
        
        # Add presigned URLs for each image
        for image in images:
            image['url'] = storage_service.generate_presigned_url(image['s3_key'])
        
        return jsonify({
            'count': len(images),
            'filter': filter_by,
            'images': images
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing images: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/v1/images/<image_id>', methods=['GET'])
@validate_request()
def get_image(image_id):
    """
    Download/view an image by ID
    ---
    tags:
      - Images
    parameters:
      - name: X-User-ID
        in: header
        required: true
        type: string
        description: User identifier
      - name: image_id
        in: path
        required: true
        type: string
        description: Image UUID
    responses:
      200:
        description: Image file (binary)
      401:
        description: Missing X-User-ID header
      404:
        description: Image not found
      500:
        description: Internal server error
    """
    try:
        user_id = request.headers.get('X-User-ID')
        
        # Get metadata
        metadata = metadata_service.get_image_metadata(image_id, user_id)
        if not metadata:
            return jsonify({'error': 'Image not found'}), 404
        
        # Download image from S3
        image_data = storage_service.get_image(metadata['s3_key'])
        if not image_data:
            return jsonify({'error': 'Failed to retrieve image'}), 500
        
        # Return image with metadata
        return send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=True,
            download_name=metadata.get('title', 'image.jpg')
        ), 200
    
    except Exception as e:
        logger.error(f"Error retrieving image: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/v1/images/<image_id>', methods=['DELETE'])
@validate_request()
def delete_image(image_id):
    """
    Delete an image and its metadata
    ---
    tags:
      - Images
    parameters:
      - name: X-User-ID
        in: header
        required: true
        type: string
        description: User identifier
      - name: image_id
        in: path
        required: true
        type: string
        description: Image UUID
    responses:
      200:
        description: Image deleted successfully
      401:
        description: Missing X-User-ID header
      404:
        description: Image not found
      500:
        description: Internal server error
    """
    try:
        user_id = request.headers.get('X-User-ID')
        
        # Get metadata
        metadata = metadata_service.get_image_metadata(image_id, user_id)
        if not metadata:
            return jsonify({'error': 'Image not found'}), 404
        
        # Delete from S3
        if not storage_service.delete_image(metadata['s3_key']):
            return jsonify({'error': 'Failed to delete image from storage'}), 500
        
        # Delete metadata from DynamoDB
        if not metadata_service.delete_metadata(image_id, user_id):
            return jsonify({'error': 'Failed to delete image metadata'}), 500
        
        return jsonify({'message': 'Image deleted successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error deleting image: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/v1/images/<image_id>', methods=['PUT'])
@validate_request()
def update_image_metadata(image_id):
    """
    Update image metadata
    ---
    tags:
      - Images
    consumes:
      - application/json
    parameters:
      - name: X-User-ID
        in: header
        required: true
        type: string
        description: User identifier
      - name: image_id
        in: path
        required: true
        type: string
        description: Image UUID
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            title:
              type: string
              example: My Updated Title
            description:
              type: string
              example: Updated description
            tags:
              type: array
              items:
                type: string
              example: [nature, sunset]
    responses:
      200:
        description: Metadata updated successfully
      401:
        description: Missing X-User-ID header
      404:
        description: Image not found
      500:
        description: Internal server error
    """
    try:
        user_id = request.headers.get('X-User-ID')
        
        # Verify image exists
        metadata = metadata_service.get_image_metadata(image_id, user_id)
        if not metadata:
            return jsonify({'error': 'Image not found'}), 404
        
        # Get update data
        data = request.get_json() or {}
        title = data.get('title')
        description = data.get('description')
        tags = data.get('tags')
        
        # Update metadata
        if not metadata_service.update_metadata(image_id, user_id, title, description, tags):
            return jsonify({'error': 'Failed to update metadata'}), 500
        
        return jsonify({'message': 'Metadata updated successfully'}), 200
    
    except Exception as e:
        logger.error(f"Error updating metadata: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    return jsonify({'error': 'File too large'}), 413


@app.errorhandler(404)
def not_found(error):
    """Handle 404 error"""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 error"""
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)
