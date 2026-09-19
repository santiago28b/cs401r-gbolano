# NorthStar Retail AI Platform — Lab 1 Foundation (dev)

Companion guide to `northstar-lab1-architecture.drawio`.
CS 401R · NorthStar Retail | 2026-09-18 | v1.0

## Nesting

```
Internet  (outside AWS)
└─ AWS Cloud — Region us-east-1
   ├─ northstar-dev-vpc  (10.0.0.0/16, DNS hostnames + resolution enabled)
   │  ├─ northstar-dev-igw        (drawn straddling the VPC boundary edge)
   │  ├─ northstar-dev-public-rt
   │  └─ Availability Zone us-east-1a
   │     └─ northstar-dev-public-1  (10.0.100.0/24, public IP on launch: yes)
   │        └─ northstar-dev-sagemaker-sg  (in: 10.0.0.0/16 only · out: all)
   │           └─ northstar-dev-domain  (SageMaker AI Studio Domain, IAM auth, ml.t3.medium)
   ├─ northstar-dev-MLEngineer   (IAM role, trust: sagemaker.amazonaws.com)
   ├─ Amazon ECR
   └─ northstar-dev-data-{account-id}  (S3: public access blocked, SSE-S3 AES-256, versioning on)
      ├─ raw/        (DataEngineer — Lab 2)
      ├─ processed/  (DataEngineer — Lab 2)
      ├─ features/   (DataEngineer — Lab 2)
      └─ artifacts/  (MLEngineer)
```

## Flow (the nine connections on the diagram)

| # | From | To | Label |
|---|------|----|-------|
| 1 | Internet | northstar-dev-igw | public traffic (bidirectional) |
| 2 | northstar-dev-igw | northstar-dev-public-rt | routes |
| 3 | northstar-dev-public-rt | northstar-dev-public-1 | 0.0.0.0/0 |
| 4 | northstar-dev-domain | northstar-dev-public-1 | runs in (bidirectional) |
| 5 | northstar-dev-domain | northstar-dev-sagemaker-sg | enforces |
| 6 | SageMaker Studio domain | northstar-dev-MLEngineer | assumes |
| 7 | northstar-dev-MLEngineer | S3 `artifacts/` | read/write (bidirectional) |
| 8 | northstar-dev-MLEngineer | S3 `features/` | read/write (bidirectional) |
| 9 | northstar-dev-MLEngineer | Amazon ECR | pull images |

No edge is drawn from the MLEngineer role to `raw/` or `processed/`. Those two prefixes
carry the red annotation **"no MLEngineer access — denied by omission"**: the role's policy
never grants them, so access is denied by default rather than by an explicit Deny.

## Resources

| Icon | Resource | Purpose |
|------|----------|---------|
| VPC boundary | `northstar-dev-vpc` — 10.0.0.0/16 | Network isolation for all Lab 1 compute |
| AZ boundary | `us-east-1a` | Single-AZ dev footprint (cost control) |
| Public subnet | `northstar-dev-public-1` — 10.0.100.0/24 | Hosts the Studio domain; auto-assigns public IPs |
| Security group | `northstar-dev-sagemaker-sg` | Inbound restricted to the VPC CIDR; outbound open |
| Internet Gateway | `northstar-dev-igw` | North/south traffic for the VPC |
| Route table | `northstar-dev-public-rt` | `0.0.0.0/0` → IGW, associated to the public subnet |
| SageMaker AI Studio Domain | `northstar-dev-domain` | IAM-auth notebooks, `ml.t3.medium` kernel |
| IAM role | `northstar-dev-MLEngineer` | Assumed by SageMaker (`sagemaker.amazonaws.com`) |
| S3 bucket | `northstar-dev-data-{account-id}` | Lake: public access blocked, SSE-S3, versioned |
| Amazon ECR | container registry | Source of training/inference images |

## Design decisions

- **Least privilege by omission.** The MLEngineer role touches only `features/` (read model
  inputs) and `artifacts/` (write models). `raw/` and `processed/` belong to the DataEngineer
  role delivered in Lab 2, so no statement in the MLEngineer policy names them.
- **Public subnet, tight security group.** The Studio domain sits in a public subnet so it can
  reach the internet through the IGW for package installs, but the SG admits inbound traffic
  only from 10.0.0.0/16 — nothing from the internet can initiate a connection to it.
- **Single AZ, single subnet.** Lab 1 is a foundation, not an HA deployment; this keeps the
  footprint inside the $200 credit budget.
- **Icons.** Every stencil is from the draw.io `mxgraph.aws4` library (the official AWS
  Architecture Icons), verified against `Sidebar-AWS4.js` before use.

## Editing / exporting

Open `northstar-lab1-architecture.drawio` in draw.io (desktop or app.diagrams.net). To export:

```bash
/Applications/draw.io.app/Contents/MacOS/draw.io -x -f png -e -b 10 \
  -o northstar-lab1-architecture.drawio.png northstar-lab1-architecture.drawio
```
