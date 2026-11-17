# Lab 5 Security and Privacy Assessment: NorthStar Churn Model

Scope: the churn pipeline from raw S3 data through Glue, the Feature Store, training, the Model Registry, and the `northstar-churn-prod` real-time endpoint with data capture.

Roles from Lab 2: **MLEngineer** (SageMaker training and serving, read/write `features/` and `artifacts/`, write `datacapture/`, no Glue), **DataEngineer** (Glue, read/write `raw/` `processed/` `features/`, Feature Store write, no write to `artifacts/`), **ModelMonitor** (CloudWatch metrics, read-only `artifacts/`, no S3 writes).

## Task 3a. STRIDE threat model

| # | Threat | STRIDE category | Likelihood | Impact | Mitigation | AWS control |
|---|---|---|---|---|---|---|
| 1 | An attacker floods the endpoint with requests so real calls (support reps) fail, and runs up the bill | Denial of Service | Medium | High | Rate limit each caller and cap how far the endpoint can scale | Amazon API Gateway usage plan with throttling in front of the endpoint, or AWS WAF rate-based rule; Application Auto Scaling `MaxCapacity = 2` in `scalable-target.json` caps instance count and cost |
| 2 | An attacker calls the endpoint many times with made-up feature values to learn who is likely to churn, or to guess if a customer was in the training data (membership inference) | Information Disclosure | Medium | High | Only the caller service can invoke the endpoint, it is not reachable from the internet, and calls are rate limited | IAM policy granting `sagemaker:InvokeEndpoint` on `endpoint/northstar-churn-prod` only to the calling role; VPC interface endpoint (AWS PrivateLink) for `sagemaker-runtime`; same throttling as row 1 |
| 3 | Stolen DataEngineer credentials are used to change raw or feature data (data poisoning) | Tampering | Low | High | **Contained by the DataEngineer role:** it has no write access to `artifacts/`, so the attacker cannot swap the deployed model. Bad data could still reach the next training run, so the CI data tests must pass before training and old object versions can be restored | IAM DataEngineer policy (writes only `raw/` `processed/` `features/`); S3 Versioning on the data bucket; CodeBuild `pre_build` pytest data validation tests (Lab 4) |
| 4 | **Gap:** one MLEngineer can train a model, approve it in the registry and ship it, and can even overwrite `model.tar.gz` in `artifacts/` after it was approved. There is no second person checking | Elevation of Privilege | Medium | High | Separation of duties: a separate approver role is the only one allowed to approve, and approved model files cannot be overwritten | New IAM ModelApprover role with `sagemaker:UpdateModelPackage`, plus an explicit Deny on that action for MLEngineer; S3 Object Lock (or Versioning + `ModelDataETag` check) on `artifacts/models/` and `artifacts/training/`. **The Lab 2 roles do not close this today** |
| 5 | Someone changes data or approves a bad model and then says "it wasn't me". The role alone does not prove it, because several people can share one role | Repudiation | Medium | Medium | Log every action with the real identity behind it, and keep old copies of data | AWS CloudTrail (management events plus S3 data events on the bucket); Model Registry `ModelApprovalStatus` history and `LastModifiedBy`; S3 Versioning keeps the previous object |

## Task 3b. Data classification

Today every prefix in the bucket uses **SSE-S3 (AES256)**: AWS encrypts with its own key, and anyone who can read the object gets it decrypted. **SSE-KMS** uses a customer managed key, which adds a second lock (you also need `kms:Decrypt` on the key) and logs every decrypt in CloudTrail. The table below is the target state.

| Asset | Tier | Encryption | IAM access policy | Share with third-party vendor? | Reason for the encryption choice |
|---|---|---|---|---|---|
| Customer PII (customer_id, hashed email, age band, state, zip) | Restricted | SSE-KMS (customer managed key) | DataEngineer only (`raw/`); nobody else reads raw PII | No | Points directly to a real person; we need the second lock and a log of every read |
| Transaction history | Confidential | SSE-KMS | DataEngineer read/write `raw/` and `processed/`; MLEngineer only sees aggregates in `features/` | No (only aggregated, de-identified data under a data processing agreement) | Purchase history tied to a customer_id can identify a person |
| Behavioral clickstream | Confidential | SSE-KMS | DataEngineer read/write; MLEngineer reads derived features only | No (aggregated only) | Browsing behavior tied to a customer is personal data |
| Product catalog | Public | SSE-S3 | All three roles read; DataEngineer writes | Yes | It is already public on the website; KMS adds cost and no protection |
| Model weights (`model.tar.gz`) | Confidential | SSE-KMS | MLEngineer write `artifacts/`; ModelMonitor read-only; endpoint runs as MLEngineer | No | Company IP, and training data can sometimes be pulled back out of a model |
| Inference logs (`datacapture/`) | Confidential | SSE-KMS (`KmsKeyId` in `DataCaptureConfig`) | Endpoint (MLEngineer) writes `datacapture/*`; ModelMonitor reads in Lab 6 | No | Each record is one customer's features plus their score; 7-day expiry plus 1-day noncurrent purge |
| Feature Store records | Confidential | SSE-KMS (online and offline store KMS keys) | DataEngineer writes; MLEngineer reads | No | Every record is a customer_id plus that customer's behavior, so it is personal data |

## Task 4. Privacy impact assessment

### Personal data inventory

| Pipeline stage | Where | Personal data |
|---|---|---|
| Raw | `s3://northstar-dev-data-031310758774/raw/customers/` | customer_id, hashed email, signup date, loyalty tier and points, preferred channel, age band, state, zip code, lifetime spend, transactions |
| Processed | `processed/customers/` | Same fields, cleaned (Glue transform) |
| Features | `features/customers/` and Feature Store `northstar-dev-customer-features` (online + offline `features/offline-store/`) | customer_id, 11 behavior features, loyalty tier, churn label |
| Training | Athena query results and model artifacts in `artifacts/` | The feature rows used to train; the model learned from them |
| Inference | `datacapture/northstar-churn-prod/` | The 11 feature values sent and the churn score returned (no customer_id in the payload) |

### Lawful basis

**Legitimate interests** (GDPR Art. 6(1)(f)). NorthStar wants to give its customers the best options: promotions and offers based on what they buy. These are loyalty members, so they would reasonably expect offers based on their purchase history. We only use purchase behavior, nothing sensitive, and customers can object to marketing at any time. Consent is weaker here because it can be withdrawn and would leave gaps in the data. Contractual necessity does not fit, because nobody needs a churn score to buy something.

### Data minimization

The model only uses the 11 behavior features (recency, tenure, purchase frequency over 30/90/180 days, order value and spend, lifetime value, basket size, category diversity, online-to-store ratio). We left out on purpose:

- **State, zip code and age band.** They are sensitive and did not help much. Zip code can act as a stand-in for income or race, and age band could lead to treating people differently by age.
- **Email (hashed).** It is only an identifier and predicts nothing.
- **Loyalty tier** is not a model input. It is only used after training to check that the model works fairly across tiers.

### Right to erasure: customer_id = C00123456

| Store | Steps |
|---|---|
| (a) Raw S3 | Rewrite `raw/customers/northstar-raw-sample.csv` without the C00123456 rows. The bucket is versioned, so also delete the old object versions (`aws s3api list-object-versions`, then `delete-object --version-id`). Re-run the Glue transform and feature jobs so `processed/` and `features/` are rebuilt without the customer. Deleting raw alone does not clean the copies already made downstream. |
| (b) Feature Store | **Online store:** `aws sagemaker-featurestore-runtime delete-record --feature-group-name northstar-dev-customer-features --record-identifier-value-as-string C00123456 --event-time <now> --deletion-mode HardDelete`. **Offline store:** it is append-only history in S3 (`features/offline-store/`), and DeleteRecord only adds a deletion marker there. We have to rewrite the Parquet files that contain the customer (Athena or Spark, filter the ID out) and delete the old versions. |
| (c) Training data and model | Delete the Athena result files in `artifacts/` that contain the customer. Then **retrain** without them, register and approve the new version, deploy it, and reject the old versions in the registry. |
| (d) Inference logs | The capture files have the 11 feature values but no customer_id, so we cannot search them by ID. They expire after 7 days and are permanently deleted 1 day later (noncurrent version expiration), so they are gone within 8 days. To make a targeted delete possible later, send an `InferenceId` with each call. |

**Hardest step: (c), the trained model.** Once it has been trained, the model has already learned from that customer, and there is no row inside the model to delete. The only way to remove it is retraining a new model without them and deploying that model. Until then, the deployed model still takes the removed data into account. The offline Feature Store is the second hardest, because it is append-only history: you rewrite whole files instead of deleting one record.
