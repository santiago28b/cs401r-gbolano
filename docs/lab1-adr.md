## ADR-001: NorthStar Platform Foundation

### Status
Accepted

### Context
[What is NorthStar building? Why does a shared AI platform need an identity model
and a storage tier structure from day one?]
NorthStar is a big company and want to build three different AI systems one one shared platform to attack a $128.5 Million yearly problem (2.1M active customers × 18% annual churn × $340 lifetime value). The reason behind the identity model and storage tier is because the bucket will be touched by the churn pipeline, the RAG and the agent. Without these boundaries and roles from the very beggining then we will having one bug could affect the whole platform if detected six months later and work could be waste. An example would be if let everyone has access to raw folder then when it gets corrupted six months later who is to blame ? everyone since if all put hands on it then everyone contributed it to its corruption. Then it is better from day one to have separation of concerns and roles well defined

### Decision
[Describe the VPC topology, S3 prefix design, and IAM role model you built.
Every rationale must tie to a NorthStar requirement — not "best practice."]

VPC topology: So far we have one vpc, one AZ, one publict subnet and sagemaker studio with a door to the internet (our internet gatway). out batch churn runs weekly so having one AZ is enough for now it AZ goes down today we can run any other day of the week.

S3 prefix desing: each folder or prefix is actaully a stage. having them in one bucke is easier to mantain and trace. ownership follows the stage, one lifecycle policy, one encryption config, one public-access-block, and cross-stage reads need no cross-bucket permissions.

IAM role model: The Engineer only has access to features and artifacts since the job is to cosume features and produce models. if a script that he makes touches raw and corrupts it then all the other system downstream of that. then having just giving him expelcit access to thos prefixes is neccesary and we avoided the other by ommision when we did not explictly add it to the permissions policy.

### Consequences
#### What this makes easy
One of the things thi acrhictecture makes easy to do is having another AZ, we could just -public-2 or something like that. It also makes easy to track who has access to raw and processed since the engineer does not have access then noone else has since we have not more roles yet. 
#### What this makes harder
if we need to deploy or run a bacth on a specific day and that day the system is down then there is not much to do. In addition if the ML engineer needs access to the raw data to check for more features that can be of help he cant do it by humself he needs having permission or talk to someone else which might delay the whole data engineering activity.
#### What would cause you to revisit this decision

Lab 2 adds a DataEngineer role and a ModelMonitor role. Right now MLEngineer is the only role, so "who can write to raw/"  is nobody but if we have someone accessign raw we might want to scope it somehow it only has read access and not full access

When we add the feature of having customer service agent handles 14,000 contacts a day and has to answer immediately. there is not weekly batch. so here we wil have to revist the only one AZ model. maybe having more and in different regions.

if another team at NorthStar starts using this same AWS account for an unrelated project. our sagemakercore is currently all access so we might want to modify that in case more projects come on the way

### Alternative Considered
[One genuinely different approach and why you rejected it]
A bucket per stage — real isolation, but four bucket policies to keep in sync, no shared lifecycle rules, and cross-stage reads get more awkward as the RAG system starts reading both processed/ and artifacts/.

An account per AI system — clean blast-radius isolation, but three of everything and no shared feature store, which defeats the point since all three systems read the same customer features

### AWS Service Selection
- Networking isolation model: Lab 1  security boundary depends on a security group that only permits inbound traffic from 10.0.0.0/16 — and the default VPC's address range and rules are AWS-assigned, so that boundary could not be expressed in Terraform or recreated identically in another account.
- Storage design: IAM can scope permission per prefix on s3 EFS has tha not equivalent 
- Identity model: related to S3 we gave it exact permission on what it needed to touch and what not using dollowing principle of least privilege
- ML development environment: user-profile structure maps onto the role model — each user profile assumes an execution role