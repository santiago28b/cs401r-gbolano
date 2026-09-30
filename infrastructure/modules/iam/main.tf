# ── modules/iam ──────────────────────────────────────────────────────────────
# Required resources (Task B1). Exactly one of each:
#
#   aws_iam_role                     MLEngineer, trusted by sagemaker.amazonaws.com
#   aws_iam_policy
#   aws_iam_role_policy_attachment
#
# Least privilege is graded in later labs, so start narrow: grant only the S3
# prefixes and SageMaker actions this role actually needs. A wildcard policy
# here will cost you points in Lab 2.

# TODO: implement the three resources above.

locals {
  role_name   = "${var.project}-${var.environment}-MLEngineer"
  policy_name = "${var.project}-${var.environment}-MLEngineerPolicy"

  # The account ID is not known to this module, so the bucket is matched by
  # wildcard. Object actions are scoped to two prefixes; a trailing * on the
  # bucket ARN alone would also match raw/ and processed/.
  bucket_arn           = "arn:aws:s3:::${var.project}-${var.environment}-data-*"
  artifacts_objects    = "arn:aws:s3:::${var.project}-${var.environment}-data-*/artifacts/*"
  features_objects     = "arn:aws:s3:::${var.project}-${var.environment}-data-*/features/*"
  raw_objects          = "arn:aws:s3:::${var.project}-${var.environment}-data-*/raw/*"
  processed_objects    = "arn:aws:s3:::${var.project}-${var.environment}-data-*/processed/*"
  glue_scripts_objects = "arn:aws:s3:::${var.project}-${var.environment}-data-*/artifacts/glue/*"
}

resource "aws_iam_role" "ml_engineer" {
  name        = local.role_name
  description = "Execution role assumed by SageMaker Studio for ML work on the NorthStar platform"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SageMakerAssume"
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = local.role_name
  }
}

resource "aws_iam_policy" "ml_engineer" {
  name        = local.policy_name
  description = "Permissions for the MLEngineer role: SageMaker, Studio self-service, scoped S3, logs, and ECR reads"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SageMakerCore"
        Effect = "Allow"
        Action = [
          "sagemaker:CreateTrainingJob",
          "sagemaker:DescribeTrainingJob",
          "sagemaker:StopTrainingJob",
          "sagemaker:CreateEndpoint",
          "sagemaker:DescribeEndpoint",
          "sagemaker:DeleteEndpoint",
          "sagemaker:CreateEndpointConfig",
          "sagemaker:DeleteEndpointConfig",
          "sagemaker:CreateMlflowApp",
          "sagemaker:DescribeMlflowApp",
          "sagemaker:ListMlflowApps",
          "sagemaker:CreatePresignedMlflowAppUrl",
          "sagemaker:RegisterModel",
          "sagemaker:DescribeModelPackage",
          "sagemaker:ListModelPackages"
        ]
        Resource = "*"
      },
      {
        Sid    = "StudioSelfService"
        Effect = "Allow"
        Action = [
          "sagemaker:DescribeDomain",
          "sagemaker:ListDomains",
          "sagemaker:DescribeUserProfile",
          "sagemaker:ListUserProfiles",
          "sagemaker:DescribeSpace",
          "sagemaker:ListSpaces",
          "sagemaker:CreateSpace",
          "sagemaker:UpdateSpace",
          "sagemaker:DeleteSpace",
          "sagemaker:DescribeApp",
          "sagemaker:ListApps",
          "sagemaker:CreateApp",
          "sagemaker:DeleteApp",
          "sagemaker:CreatePresignedDomainUrl"
        ]
        Resource = [
          "arn:aws:sagemaker:*:*:domain/*",
          "arn:aws:sagemaker:*:*:user-profile/*",
          "arn:aws:sagemaker:*:*:space/*",
          "arn:aws:sagemaker:*:*:app/*"
        ]
      },
      {
        Sid    = "S3ArtifactsAndFeatures"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          local.artifacts_objects,
          local.features_objects
        ]
      },
      {
        Sid    = "S3BucketList"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = local.bucket_arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/sagemaker/*"
      },
      {
        Sid    = "ECRRead"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = local.policy_name
  }
}

resource "aws_iam_role_policy_attachment" "ml_engineer" {
  role       = aws_iam_role.ml_engineer.name
  policy_arn = aws_iam_policy.ml_engineer.arn
}

resource "aws_iam_role" "data_engineer" {
  name        = "${var.project}-${var.environment}-DataEngineer"
  description = "Execution role for Glue ETL jobs and Feature Store ingestion"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DataServicesAssume"
      Effect    = "Allow"
      Principal = { Service = ["glue.amazonaws.com", "lambda.amazonaws.com", "sagemaker.amazonaws.com"] }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${var.project}-${var.environment}-DataEngineer" }
}

resource "aws_iam_policy" "data_engineer" {
  name        = "${var.project}-${var.environment}-DataEngineerPolicy"
  description = "Permissions for the DataEngineer role: SageMaker, ec2, scoped S3, logs, and glue"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GlueFull"
        Effect = "Allow"
        Action = [
          "glue:*"
        ]
        Resource = "*"
      },
      {
        Sid    = "ENILifecycle"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeRouteTables",
          "ec2:DescribeVpcEndpoints",
          "ec2:DescribeVpcAttribute"
        ]
        Resource = "*"
      },
      {
        Sid    = "ENITags"
        Effect = "Allow"
        Action = [
          "ec2:CreateTags",
          "ec2:DeleteTags"
        ]
        Resource = "arn:aws:ec2:*:*:network-interface/*"
      },
      {
        Sid    = "S3DataStages"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          local.raw_objects,
          local.processed_objects,
          local.features_objects
        ]
      },
      {
        Sid    = "S3FeatureStoreAcl"
        Effect = "Allow"
        Action = [
          "s3:PutObjectAcl"
        ]
        Resource = local.features_objects
      },
      {
        Sid    = "S3ReadGlueScripts"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = local.glue_scripts_objects
      },
      {
        Sid    = "S3Bucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:GetBucketAcl"
        ]
        Resource = local.bucket_arn
      },
      {
        Sid    = "FeatureStoreWrite"
        Effect = "Allow"
        Action = [
          "sagemaker:PutRecord",
          "sagemaker:CreateFeatureGroup",
          "sagemaker:DescribeFeatureGroup"
        ]
        Resource = "arn:aws:sagemaker:*:*:feature-group/*"
      },
      {
        Sid    = "GlueLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws-glue/*"
      }

    ]
  })

  tags = {
    Name = "${var.project}-${var.environment}-DataEngineerPolicy"
  }
}

resource "aws_iam_role_policy_attachment" "data_engineer" {
  role       = aws_iam_role.data_engineer.name
  policy_arn = aws_iam_policy.data_engineer.arn
}

resource "aws_iam_role" "model_monitor" {
  name        = "${var.project}-${var.environment}-ModelMonitor"
  description = "Execution role for Monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "SageMakerAssume"
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Name = "${var.project}-${var.environment}-ModelMonitor" }
}

resource "aws_iam_policy" "model_monitor" {
  name        = "${var.project}-${var.environment}-ModelMonitorPolicy"
  description = "Model monitor role"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Sid    = "ProcessingJobsReadOnly"
        Effect = "Allow"
        Action = [
          "sagemaker:ListProcessingJobs",
          "sagemaker:DescribeProcessingJob"
        ]
        Resource = "*"
      },
      {
        Sid      = "S3ReadArtifacts"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = local.artifacts_objects
      },
      {
        Sid      = "S3Bucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = local.bucket_arn
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/sagemaker/*"
      }
    ]
  })
  tags = { Name = "${var.project}-${var.environment}-ModelMonitorPolicy" }
}

resource "aws_iam_role_policy_attachment" "model_monitor" {
  role       = aws_iam_role.model_monitor.name
  policy_arn = aws_iam_policy.model_monitor.arn
}
