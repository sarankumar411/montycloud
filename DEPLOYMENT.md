# Deployment Guide

## Overview

This guide covers deploying the Image Upload Service to AWS production environments.

---

## Deployment Options

### 1. AWS Lambda + API Gateway (Recommended for Serverless)

#### Advantages
- Pay per request
- Automatic scaling
- No server management
- Cost-effective for variable loads

#### Setup Steps

**Step 1: Install Serverless Framework**
```bash
npm install -g serverless
serverless --version
```

**Step 2: Create Serverless Config**

Create `serverless.yml`:
```yaml
service: image-upload-service

provider:
  name: aws
  runtime: python3.9
  region: us-east-1
  environment:
    S3_BUCKET_NAME: image-uploads-prod
    DYNAMODB_TABLE_NAME: images-metadata-prod
  iamRoleStatements:
    - Effect: Allow
      Action:
        - s3:*
        - dynamodb:*
      Resource: "*"

functions:
  api:
    handler: app.app
    events:
      - http:
          path: /{proxy+}
          method: ANY
          cors: true
      - http:
          path: /
          method: ANY
          cors: true

plugins:
  - serverless-python-requirements
  - serverless-wsgi

custom:
  wsgi:
    app: app.app
    packRequirements: false
  pythonRequirements:
    dockerizePip: true
```

**Step 3: Deploy**
```bash
serverless deploy --stage prod --region us-east-1
```

**Step 4: Monitor**
```bash
serverless logs -f api --stage prod
```

---

### 2. ECS/Fargate (Recommended for Container-based)

#### Advantages
- Full control over container environment
- Consistent performance
- Easier integration with existing services
- Better for CPU-intensive operations

#### Setup Steps

**Step 1: Create Docker Image**

Create `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
```

Build and test locally:
```bash
docker build -t image-upload-service:1.0 .
docker run -p 5000:5000 image-upload-service:1.0
```

**Step 2: Push to ECR**
```bash
# Create ECR repository
aws ecr create-repository \
  --repository-name image-upload-service \
  --region us-east-1

# Get login token
aws ecr get-login-password --region us-east-1 | docker login \
  --username AWS \
  --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Tag image
docker tag image-upload-service:1.0 \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/image-upload-service:1.0

# Push image
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/image-upload-service:1.0
```

**Step 3: Create ECS Task Definition**

Create `task-definition.json`:
```json
{
  "family": "image-upload-service",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "image-upload-service",
      "image": "<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/image-upload-service:1.0",
      "portMappings": [
        {
          "containerPort": 5000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "S3_BUCKET_NAME",
          "value": "image-uploads-prod"
        },
        {
          "name": "DYNAMODB_TABLE_NAME",
          "value": "images-metadata-prod"
        },
        {
          "name": "AWS_REGION",
          "value": "us-east-1"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/image-upload-service",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/image-upload-service-role"
}
```

Register task definition:
```bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json
```

**Step 4: Create ECS Service**
```bash
aws ecs create-service \
  --cluster image-upload-cluster \
  --service-name image-upload-service \
  --task-definition image-upload-service \
  --desired-count 2 \
  --launch-type FARGATE \
  --load-balancers targetGroupArn=<ALB_TARGET_GROUP_ARN>,containerName=image-upload-service,containerPort=5000 \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

---

### 3. EC2 + Auto Scaling (For Full Control)

#### Advantages
- Maximum control
- Custom configuration
- Suitable for complex setups

#### Setup Steps

**Step 1: Create AMI with Application**

```bash
# Launch EC2 instance with Ubuntu 20.04
# SSH into instance and run:

sudo apt-get update
sudo apt-get install -y python3-pip
sudo apt-get install -y git

git clone <your-repo-url>
cd image-upload-service
pip install -r requirements.txt

# Create systemd service
sudo tee /etc/systemd/system/image-upload.service > /dev/null <<EOF
[Unit]
Description=Image Upload Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/image-upload-service
ExecStart=/usr/bin/python3 /home/ubuntu/image-upload-service/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable image-upload.service
sudo systemctl start image-upload.service
```

Create AMI from instance

**Step 2: Create Launch Template**
```bash
aws ec2 create-launch-template \
  --launch-template-name image-upload-service \
  --version-description "v1" \
  --launch-template-data '{
    "ImageId":"ami-xxxxxxxx",
    "InstanceType":"t3.medium",
    "IamInstanceProfile":{"Name":"image-upload-service-role"},
    "UserData":"<base64-encoded-init-script>"
  }'
```

**Step 3: Create Auto Scaling Group**
```bash
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name image-upload-asg \
  --launch-template LaunchTemplateName=image-upload-service,Version=\$Latest \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-xxx,subnet-yyy" \
  --target-group-arns arn:aws:elasticloadbalancing:...
```

---

## Pre-Deployment Checklist

### AWS Account Setup

- [ ] AWS Account created
- [ ] IAM user with appropriate permissions
- [ ] S3 bucket created (`image-uploads-prod`)
- [ ] DynamoDB table created (`images-metadata-prod`)
- [ ] RDS/DynamoDB backups configured
- [ ] CloudWatch log groups created

### Application Configuration

- [ ] .env file with production values
- [ ] AWS credentials configured
- [ ] SSL/TLS certificates (if using custom domain)
- [ ] API rate limiting configured
- [ ] Logging level set to INFO/WARNING
- [ ] Database backups tested

### Security Setup

- [ ] Security groups configured
- [ ] Network ACLs configured
- [ ] WAF rules configured (if using ALB)
- [ ] S3 bucket encryption enabled
- [ ] DynamoDB encryption enabled
- [ ] VPC endpoints configured (if needed)
- [ ] Secrets stored in AWS Secrets Manager

### Monitoring & Logging

- [ ] CloudWatch alarms created
- [ ] Log retention policies set
- [ ] Metrics dashboard created
- [ ] Error alerting configured
- [ ] Performance thresholds set

---

## Production Configuration

### Environment Variables

Update `.env` for production:

```env
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<PRODUCTION_KEY>
AWS_SECRET_ACCESS_KEY=<PRODUCTION_SECRET>

# Remove LocalStack for production
# LOCALSTACK_ENDPOINT=...

# S3 Configuration
S3_BUCKET_NAME=image-uploads-prod
MAX_FILE_SIZE=52428800  # 50MB

# DynamoDB Configuration
DYNAMODB_TABLE_NAME=images-metadata-prod

# Flask Configuration
FLASK_ENV=production
DEBUG=false

# Additional Production Settings
LOG_LEVEL=INFO
ENABLE_METRICS=true
ENABLE_CORS=true
CORS_ORIGINS=https://example.com
```

### AWS Credentials

**Using IAM Roles (Recommended for Serverless/Containers):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::image-uploads-prod/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/images-metadata-prod*"
    }
  ]
}
```

---

## Database Migration

### Create DynamoDB Table in Production

```bash
aws dynamodb create-table \
  --table-name images-metadata-prod \
  --attribute-definitions \
    AttributeName=image_id,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
    AttributeName=title,AttributeType=S \
  --key-schema \
    AttributeName=image_id,KeyType=HASH \
    AttributeName=user_id,KeyType=RANGE \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "user_id-created_at-index",
        "KeySchema": [
          {"AttributeName":"user_id","KeyType":"HASH"},
          {"AttributeName":"created_at","KeyType":"RANGE"}
        ],
        "Projection": {"ProjectionType":"ALL"},
        "ProvisionedThroughput": {"ReadCapacityUnits":25,"WriteCapacityUnits":25}
      },
      {
        "IndexName": "title-created_at-index",
        "KeySchema": [
          {"AttributeName":"title","KeyType":"HASH"},
          {"AttributeName":"created_at","KeyType":"RANGE"}
        ],
        "Projection": {"ProjectionType":"ALL"},
        "ProvisionedThroughput": {"ReadCapacityUnits":25,"WriteCapacityUnits":25}
      }
    ]' \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=25,WriteCapacityUnits=25 \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --stream-specification StreamViewType=NEW_AND_OLD_IMAGES \
  --region us-east-1
```

### Create S3 Bucket

```bash
aws s3api create-bucket \
  --bucket image-uploads-prod \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket image-uploads-prod \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket image-uploads-prod \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket image-uploads-prod \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

---

## Scaling Configuration

### DynamoDB Auto-Scaling

```bash
# Enable auto-scaling for table
aws application-autoscaling register-scalable-target \
  --service-namespace dynamodb \
  --scalable-dimension dynamodb:table:WriteCapacityUnits \
  --resource-id table/images-metadata-prod \
  --min-capacity 5 \
  --max-capacity 100

# Create scaling policy
aws application-autoscaling put-scaling-policy \
  --policy-name dynamodb-scaling \
  --service-namespace dynamodb \
  --scalable-dimension dynamodb:table:WriteCapacityUnits \
  --resource-id table/images-metadata-prod \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "DynamoDBWriteCapacityUtilization"
    }
  }'
```

### ECS Auto-Scaling

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/default/image-upload-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Create scaling policy
aws application-autoscaling put-scaling-policy \
  --policy-name ecs-scaling \
  --service-namespace ecs \
  --resource-id service/default/image-upload-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }'
```

---

## Monitoring & Alerts

### CloudWatch Alarms

```bash
# API error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name image-upload-api-errors \
  --alarm-description "Alert when API error rate is high" \
  --metric-name 4XXError \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>

# DynamoDB throttling alarm
aws cloudwatch put-metric-alarm \
  --alarm-name dynamodb-throttling \
  --alarm-description "Alert on DynamoDB throttling" \
  --metric-name UserErrors \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 60 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=TableName,Value=images-metadata-prod \
  --alarm-actions <SNS_TOPIC_ARN>
```

### CloudWatch Logs

```bash
# Create log group
aws logs create-log-group --log-group-name /image-upload-service/api

# Set retention
aws logs put-retention-policy \
  --log-group-name /image-upload-service/api \
  --retention-in-days 30

# Create metric filter
aws logs put-metric-filter \
  --log-group-name /image-upload-service/api \
  --filter-name APIErrors \
  --filter-pattern "[ERROR]" \
  --metric-transformations \
  metricName=APIErrors,metricNamespace=ImageUploadService,metricValue=1
```

---

## CI/CD Integration

### GitHub Actions Example

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
      - run: pytest test_app.py -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to AWS
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          pip install serverless
          serverless deploy --stage prod
```

---

## Rollback Procedure

### If Deployment Fails

```bash
# Rollback Lambda version
aws lambda update-alias \
  --function-name image-upload-service \
  --name prod \
  --function-version <PREVIOUS_VERSION>

# Rollback ECS task definition
aws ecs update-service \
  --cluster image-upload-cluster \
  --service image-upload-service \
  --task-definition image-upload-service:<PREVIOUS_REVISION>
```

---

## Health Check & Monitoring

```bash
# Test API endpoint
curl https://api.example.com/health

# Check application logs
aws logs tail /image-upload-service/api --follow

# Monitor metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 300 \
  --statistics Average,Maximum
```

---

## Post-Deployment

- [ ] Test all API endpoints
- [ ] Verify database connectivity
- [ ] Check CloudWatch logs
- [ ] Validate monitoring alerts
- [ ] Load test the service
- [ ] Document any issues
- [ ] Update runbooks
- [ ] Notify stakeholders

---

## Support & Troubleshooting

### Common Issues

**Lambda Timeout**
- Increase timeout in serverless.yml (default: 30s)
- Optimize code performance
- Check DynamoDB/S3 response times

**DynamoDB Throttling**
- Increase provisioned capacity
- Enable auto-scaling
- Optimize query patterns

**S3 Upload Failures**
- Verify bucket exists and is accessible
- Check IAM permissions
- Enable S3 Transfer Acceleration

**High Costs**
- Review CloudWatch metrics
- Adjust DynamoDB capacity
- Implement caching
- Use S3 Intelligent-Tiering

---

For more information, see README.md and ARCHITECTURE.md
