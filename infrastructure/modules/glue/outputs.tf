output "database_name" {
  description = "Name of the Glue catalog database"
  value       = aws_glue_catalog_database.this.name
}

output "crawler_name" {
  description = "Name of the crawler over raw/customers/"
  value       = aws_glue_crawler.raw.name
}
