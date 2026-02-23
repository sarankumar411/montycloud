import os
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')

# S3 Configuration
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'image-uploads')
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# DynamoDB Configuration
DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME', 'images-metadata')

# Flask Configuration
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
DEBUG = FLASK_ENV == 'development'

# Supported image formats
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
