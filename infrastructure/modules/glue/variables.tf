variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "bucket_name" {
  description = "Data bucket holding raw/, processed/ and artifacts/glue/"
  type        = string
}

variable "data_engineer_role_arn" {
  description = "IAM role the crawler and ETL job run as (the DataEngineer role)"
  type        = string
}

variable "subnet_id" {
  description = "Private subnet the Glue network connection places workers in"
  type        = string
}

variable "security_group_id" {
  description = "Security group for Glue workers; must have a self-referencing all-traffic ingress rule"
  type        = string
}

variable "availability_zone" {
  description = "Availability Zone of the private subnet"
  type        = string
}

variable "feature_group_name" {
  description = "Feature Group the feature engineering job ingests into"
  type        = string
}

variable "region" {
  description = "AWS region for the Feature Store runtime client"
  type        = string
}
