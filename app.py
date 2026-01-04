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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

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
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


@app.route('/api/v1/images/upload', methods=['POST'])
@validate_request()
def upload_image():
    """
    Upload image with metadata
    
    Required Headers:
        X-User-ID: User identifier
    
    Form Data:
        file: Image file (required)
        title: Image title (optional)
        description: Image description (optional)
        tags: Comma-separated tags (optional)
    
    Returns:
        201: Image uploaded successfully with metadata
        400: Bad request (missing file, invalid format, etc.)
        413: File too large
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
    List images with filters
    
    Required Headers:
        X-User-ID: User identifier
    
    Query Parameters:
        filter_by: 'user' (default) or 'tags' or 'title'
        user_id: User ID to filter by (required if filter_by=user)
        tags: Comma-separated tags to filter by (required if filter_by=tags)
        title: Title to search by (required if filter_by=title)
        limit: Number of results (default: 10, max: 100)
    
    Returns:
        200: List of images
        400: Bad request (invalid parameters)
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
    Download/view image
    
    Required Headers:
        X-User-ID: User identifier
    
    Returns:
        200: Image file
        404: Image not found
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
    Delete image
    
    Required Headers:
        X-User-ID: User identifier
    
    Returns:
        200: Image deleted successfully
        404: Image not found
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
    
    Required Headers:
        X-User-ID: User identifier
    
    JSON Body:
        title: Updated title (optional)
        description: Updated description (optional)
        tags: Updated tags list (optional)
    
    Returns:
        200: Metadata updated successfully
        404: Image not found
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
