variable "project" {
  description = "Project name, used as the first element of every resource name"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "bucket_name" {
  description = "Data bucket; the offline store writes under features/offline-store/"
  type        = string
}

variable "data_engineer_role_arn" {
  description = "Execution role feature store uses to write the offline store (DataEngineer)"
  type        = string
}
