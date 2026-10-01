# ── modules/glue ─────────────────────────────────────────────────────────────
# Catalog database, crawler over raw/customers/, script upload, VPC network
# connection, and the transform ETL job.

resource "aws_glue_catalog_database" "this" {
  name = "${var.project}_${var.environment}" # underscore, not hyphen
}

resource "aws_glue_crawler" "raw" {
  name          = "${var.project}-${var.environment}-raw-crawler"
  role          = var.data_engineer_role_arn
  database_name = aws_glue_catalog_database.this.name

  s3_target {
    path = "s3://${var.bucket_name}/raw/customers/"
  }
}

# (a) Upload the script. Glue can only run scripts stored in S3.
resource "aws_s3_object" "transform_script" {
  bucket = var.bucket_name
  key    = "artifacts/glue/transform.py"
  source = "${path.module}/../../../glue-scripts/transform.py"
  etag   = filemd5("${path.module}/../../../glue-scripts/transform.py")
}

# (b) Tell Glue to run its workers inside the private subnet.
resource "aws_glue_connection" "vpc" {
  name            = "${var.project}-${var.environment}-vpc-connection"
  connection_type = "NETWORK"

  physical_connection_requirements {
    availability_zone      = var.availability_zone
    subnet_id              = var.subnet_id # the PRIVATE subnet
    security_group_id_list = [var.security_group_id]
  }
}

# (c) The ETL job that runs transform.py.
resource "aws_glue_job" "transform" {
  name              = "${var.project}-${var.environment}-transform"
  role_arn          = var.data_engineer_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30 # minutes; a safety cap on cost
  connections       = [aws_glue_connection.vpc.name]

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.transform_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--database_name" = aws_glue_catalog_database.this.name
    "--table_name"    = "customers"
    "--output_path"   = "s3://${var.bucket_name}/processed/customers/"
  }
}
