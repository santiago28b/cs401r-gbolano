## Data Contract: processed/customers

### Producer
Team / process: Glue ETL job `northstar-dev-transform`

### Consumers
- Feature engineering job `northstar-dev-feature-engineer`
- (Future) Direct model training in Lab 3

### Grain
One row per transaction. A customer appears on many rows.

### Schema
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `transaction_id` | string | No | Unique ID of one purchase, format `TXN-` + 12 letters/digits. Natural key, one row per value |
| `customer_id` | string | No | Customer who made the purchase, format `CUST-` + 8 digits. Trimmed. Rows without it are dropped. Repeats across rows |
| `purchase_date` | date | No | Day of the purchase. Source had ISO and MM/DD/YYYY formats, both parsed to a date |
| `order_value` | double | No | Gross order value in USD. Missing values (~4%) filled with the column median |
| `num_items` | int | No | Number of line items in the order. Missing values filled with the rounded median |
| `payment_method` | string | No | `cash`, `credit_card`, `debit_card` or `gift_card`. Missing values set to `unknown` |
| `channel` | string | No | `store` or `online`. Missing values set to `unknown` |
| `store_id` | string | No | `STORE-` + 3 digits for in-store orders, `ONLINE` for online orders. Missing values set to `unknown` |
| `product_category` | string | No | Main category of the order, one of 8 values. Missing values (~2%) set to `unknown` |

### Quality Guarantees
- `customer_id` is never null
- No duplicate `transaction_id` rows (a `customer_id` repeating across rows is expected, not a defect)
- `order_value` is between 15.00 and 620.00 USD, never negative or zero
- `num_items` is a whole number between 1 and 9
- `purchase_date` falls between 2025-04-01 and 2026-06-30
- `channel` is only `store`, `online` or `unknown`
- No column has null values after the transform (missing values are imputed, rows without `customer_id` are dropped)
- `purchase_date` is a valid ISO 8601 date

### SLA
- Data is available in `processed/customers/` within 2 hours of landing in `raw/customers/`

### Versioning
- Schema changes require a new S3 prefix (e.g., `processed/customers/v2/`)
- Breaking changes require consumer notification 5 business days in advance