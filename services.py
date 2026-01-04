import boto3
from botocore.exceptions import ClientError
from config import LOCALSTACK_ENDPOINT, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AWSClientFactory:
    """Factory for creating AWS service clients"""
    
    _s3_client = None
    _dynamodb_client = None
    _dynamodb_resource = None
    
    @staticmethod
    def get_s3_client():
        """Get or create S3 client"""
        if AWSClientFactory._s3_client is None:
            AWSClientFactory._s3_client = boto3.client(
                's3',
                endpoint_url=LOCALSTACK_ENDPOINT,
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                use_ssl=False
            )
        return AWSClientFactory._s3_client
    
    @staticmethod
    def get_dynamodb_client():
        """Get or create DynamoDB client"""
        if AWSClientFactory._dynamodb_client is None:
            AWSClientFactory._dynamodb_client = boto3.client(
                'dynamodb',
                endpoint_url=LOCALSTACK_ENDPOINT,
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                use_ssl=False
            )
        return AWSClientFactory._dynamodb_client
    
    @staticmethod
    def get_dynamodb_resource():
        """Get or create DynamoDB resource"""
        if AWSClientFactory._dynamodb_resource is None:
            AWSClientFactory._dynamodb_resource = boto3.resource(
                'dynamodb',
                endpoint_url=LOCALSTACK_ENDPOINT,
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                use_ssl=False
            )
        return AWSClientFactory._dynamodb_resource


class ImageStorageService:
    """Service for handling image storage in S3"""
    
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.s3_client = AWSClientFactory.get_s3_client()
    
    def create_bucket_if_not_exists(self) -> bool:
        """Create S3 bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} already exists")
            return True
        except ClientError as e:
            # If the bucket doesn't exist, create it. Otherwise log and fail.
            error_code = e.response.get('Error', {}).get('Code')
            if error_code in ("404", "NoSuchBucket", "NotFound"):
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket {self.bucket_name}")
                    return True
                except ClientError as ce:
                    logger.error(f"Error creating bucket: {str(ce)}")
                    return False
            logger.error(f"Error checking bucket existence: {str(e)}")
            return False
    
    def upload_image(self, image_data: bytes, file_name: str) -> Optional[str]:
        """
        Upload image to S3
        Returns: S3 object key if successful, None otherwise
        """
        try:
            s3_key = f"images/{uuid.uuid4()}/{file_name}"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_data,
                ContentType='image/jpeg'
            )
            logger.info(f"Uploaded image to {s3_key}")
            return s3_key
        except Exception as e:
            logger.error(f"Error uploading image: {str(e)}")
            return None
    
    def delete_image(self, s3_key: str) -> bool:
        """Delete image from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted image {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting image: {str(e)}")
            return False
    
    def get_image(self, s3_key: str) -> Optional[bytes]:
        """Download image from S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Error retrieving image: {str(e)}")
            return None
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate presigned URL for image access"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None


class ImageMetadataService:
    """Service for handling image metadata in DynamoDB"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.dynamodb = AWSClientFactory.get_dynamodb_resource()
        self.dynamodb_client = AWSClientFactory.get_dynamodb_client()
    
    def create_table_if_not_exists(self) -> bool:
        """Create DynamoDB table if it doesn't exist"""
        try:
            self.dynamodb.Table(self.table_name).table_status
            logger.info(f"Table {self.table_name} already exists")
            return True
        except ClientError:
            try:
                table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {'AttributeName': 'image_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'user_id', 'KeyType': 'RANGE'}
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'image_id', 'AttributeType': 'S'},
                        {'AttributeName': 'user_id', 'AttributeType': 'S'},
                        {'AttributeName': 'created_at', 'AttributeType': 'S'},
                        {'AttributeName': 'title', 'AttributeType': 'S'}
                    ],
                    GlobalSecondaryIndexes=[
                        {
                            'IndexName': 'user_id-created_at-index',
                            'KeySchema': [
                                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                                {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                            ],
                            'Projection': {'ProjectionType': 'ALL'},
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 5,
                                'WriteCapacityUnits': 5
                            }
                        },
                        {
                            'IndexName': 'title-created_at-index',
                            'KeySchema': [
                                {'AttributeName': 'title', 'KeyType': 'HASH'},
                                {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                            ],
                            'Projection': {'ProjectionType': 'ALL'},
                            'ProvisionedThroughput': {
                                'ReadCapacityUnits': 5,
                                'WriteCapacityUnits': 5
                            }
                        }
                    ],
                    BillingMode='PROVISIONED',
                    ProvisionedThroughput={
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                )
                table.wait_until_exists()
                logger.info(f"Created table {self.table_name}")
                return True
            except ClientError as e:
                logger.error(f"Error creating table: {str(e)}")
                return False
    
    def save_metadata(self, user_id: str, image_id: str, s3_key: str, 
                     title: str, description: str, tags: List[str]) -> bool:
        """Save image metadata to DynamoDB"""
        try:
            table = self.dynamodb.Table(self.table_name)
            table.put_item(
                Item={
                    'image_id': image_id,
                    'user_id': user_id,
                    's3_key': s3_key,
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
            )
            logger.info(f"Saved metadata for image {image_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving metadata: {str(e)}")
            return False
    
    def get_image_metadata(self, image_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get image metadata from DynamoDB"""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.get_item(
                Key={'image_id': image_id, 'user_id': user_id}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error retrieving metadata: {str(e)}")
            return None
    
    def list_images_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List all images for a user"""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.query(
                IndexName='user_id-created_at-index',
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id},
                ScanIndexForward=False,  # Order by creation time descending
                Limit=limit
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error listing images: {str(e)}")
            return []
    
    def search_images_by_title(self, title: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search images by title"""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.query(
                IndexName='title-created_at-index',
                KeyConditionExpression='title = :title',
                ExpressionAttributeValues={':title': title},
                ScanIndexForward=False,
                Limit=limit
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error searching by title: {str(e)}")
            return []
    
    def search_images_by_tags(self, user_id: str, tags: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Search images by tags"""
        try:
            table = self.dynamodb.Table(self.table_name)
            # First get all images for the user, then filter by tags
            response = table.query(
                IndexName='user_id-created_at-index',
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id},
                ScanIndexForward=False,
                Limit=limit * 2  # Get more items to filter
            )
            
            items = response.get('Items', [])
            filtered_items = []
            for item in items:
                item_tags = set(item.get('tags', []))
                if any(tag in item_tags for tag in tags):
                    filtered_items.append(item)
                if len(filtered_items) >= limit:
                    break
            return filtered_items
        except Exception as e:
            logger.error(f"Error searching by tags: {str(e)}")
            return []
    
    def delete_metadata(self, image_id: str, user_id: str) -> bool:
        """Delete image metadata from DynamoDB"""
        try:
            table = self.dynamodb.Table(self.table_name)
            table.delete_item(
                Key={'image_id': image_id, 'user_id': user_id}
            )
            logger.info(f"Deleted metadata for image {image_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting metadata: {str(e)}")
            return False
    
    def update_metadata(self, image_id: str, user_id: str, 
                       title: Optional[str] = None, 
                       description: Optional[str] = None,
                       tags: Optional[List[str]] = None) -> bool:
        """Update image metadata"""
        try:
            table = self.dynamodb.Table(self.table_name)
            update_expr = "SET updated_at = :updated_at"
            expr_values = {':updated_at': datetime.utcnow().isoformat()}
            
            if title:
                update_expr += ", title = :title"
                expr_values[':title'] = title
            if description:
                update_expr += ", description = :description"
                expr_values[':description'] = description
            if tags:
                update_expr += ", tags = :tags"
                expr_values[':tags'] = tags
            
            table.update_item(
                Key={'image_id': image_id, 'user_id': user_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            logger.info(f"Updated metadata for image {image_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating metadata: {str(e)}")
            return False
