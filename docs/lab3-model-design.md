# Lab 3 — Model Design Justification

**Track declaration: Track A (churn prediction) + Track B (RAG offer generation)**

---

## 1. Churn model: why gradient boosting

The reason that we use XGBoost is that I feel it's one of the most used in the industry. It is used in Kaggle competitions, and also it's used with different types of datasets. In this case, we have 10,000 customers with 11 features that we created or got from filtering and processing the data. XGBoost is great for prediction and classification. In this case, it helps us to predict the churn score.

The way XGBoost works is gradient boosting: it builds many small decision trees one after another, and each new tree learns from the mistakes of the trees before it. That is why it performs well and trains fast on tabular data like ours. 

The reason we are using gradient boosting is that it is the most efficient fit for this data. For instance, if we were to use logistic regression, it would miss interactions like "frequent buyer, plus slowing down," because it treats each feature on its own in a straight line. A neural network, I think, is overkill for 10,000 rows, and the team can't see what is happening behind the scenes. For interpretability, the retention team needs to know why a customer was flagged, and the feature-importance (gain) plot gives that. What would make me switch is millions of rows, sequence data (like clickstream), or a requirement for a simple linear model.

## 2. What the features bought us

| Model | Test AUC |
|---|---|
| Recency-only XGBoost (`days_since_last_purchase`) | 0.7233 |
| Full model (11 features) | 0.7804 |
| Lift (95% CI, paired bootstrap) | +0.0571 [0.0373, 0.0756] |

We can see that just a simple rule using XGBoost for days in last purchase has an area under the curve of 0.7233. However, when we do some data cleaning, feature engineering, and processing, we have an area under the curve of 0.7804 and also a 95% confidence interval. The confidence interval [0.037, 0.076] is entirely above zero, so the model beats the simple rule consistently, not just on one lucky split. Even though it is a modest change, it is positive, and it is based on the data, so it's not just luck. For this reason, I believe that this is a model that is worth paying for and paying attention to. With more data and retraining, I expect it to keep improving.

The features that did the work were `purchase_frequency_180d`, `days_since_last_purchase`, and `purchase_frequency_30d`. Those are the ones with the highest gain in the feature-importance plot, so they did the most to separate likely churners from customers who stay. The weak features were `category_diversity_score`, `online_to_store_ratio`, and `customer_tenure_days`. Even though they were built to catch churners who still look active, they added little gain, just a tiny portion compared to the strong features.

## 3. LLM system: why RAG over fine-tuning

So, the reasons why we're using RAG instead of fine-tuning: the main one is that policies change. Say tier thresholds, return windows and shipping rules get updated. With fine-tuning, the old rule stays in the weights. Changing it means new training data, retraining, retesting, and redeploying. Until then, the model confidently quotes the old policy.

In contrast, with RAG, we just edit the policy doc, rerun `rag/ingest.py` (29 chunks, seconds), and then we're done. It is especially good for this kind of data that we have. We don't have much data, and fine-tuning needs a lot more data (hundreds or thousands of example offers); the whole policy corpus is only about 4,700 words.

The main production risk of RAG is that the model can still misstate a policy it was given. We saw that in failure 2: the model can misstate a return policy, like when it stated that the 60-day return window was for specific categories and not for all merchandise. The RAGAS judge did not catch it (faithfulness 0.88), so automated evaluation alone is not enough.

Another thing is the tier gap. The feature store tier comes from lifetime value, but the policy defines tiers by trailing 12-month spend. For a customer near a threshold, the two can disagree. What we can do is just have the model phrase it in a way that it doesn't state your current status, but it is a conditional, like "As a Gold member, you currently...". For the long term, I think it is better to read the tier from the system of record at generation time.

### Pipeline choices

| Choice | What I used |
|---|---|
| Embedding model | Titan Text Embeddings V2 (1024-d, normalized) |
| Vector store | FAISS `IndexFlatIP`, local |
| Chunking | split on the `---` section dividers, keep pieces that start with a `##` heading; no overlap; doc title + ID prefixed (29 chunks) |
| Retrieval | K=4; multi-query (3 queries, round-robin merge) |
| Generation model | Claude Haiku 4.5 (`us.` inference profile), temperature 0.2 |
| Re-ranking | none |

On the pipeline choices:
- For the embedding, we used the Titan Text Embedding V2, which runs natively on Bedrock: same account, same IAM, no extra vendor. It has 1,024 dimensions, which is plenty for 29 chunks. The alternative was a tool called Cohere Embed, which is also on Bedrock and is strong, but there's no reason to add a second vendor for a tiny English corpus.
- For the vector store, we use FAISS locally. The reason is that it's only 29 vectors: exact search over 29 is instant and free, with nothing to deploy or tear down. Another alternative would be OpenSearch Serverless, but it is overkill here and it charges even when it's idle.
- For the chunking, we split each doc on its `---` section dividers and keep only the pieces that start with a `##` heading, so each chunk is one numbered policy section with its subsections. We do that so we don't cut a rule in half, so we don't need overlap. An alternative would be fixed-size chunks, like, say, 200 words with 50 overlap, but I don't think that would be a good idea because a fixed cut can split a rule from its condition (for example "Platinum gets 60 days" from "on all eligible merchandise").
- For retrieval, we use k = 4. With a single query, retrieval was customer-blind and everyone got almost the same chunks. Multi-query matches what this customer needs. k stays at 4 to keep the comparison fair. An alternative would be a single query, or a bigger k means more noise in the prompt. 
- For the generator, we use Claude Haiku 4.5 with a temperature of 0.2. Since the output is only 2-3 sentences, Haiku is fast and cheap. Low temperature keeps it close to the policy text, and the `us.` inference profile keeps data in US regions. There are multiple alternatives: one of them is Claude Sonnet, which the lab measured raises faithfulness by about 0.1, but it costs several times more per token, and I don't think that is worth it for 2-3 sentence offers.
- On re-ranking: with 29 chunks and k = 4, the first retrieval is already a short list, so a re-ranker would have little to reorder. I would add one if the corpus grows.

## 4. What I would do differently with 10x the time or data

I think what I would do is add a claim checker step. If I have more time and more data, after generating the offer, a second call checks each claim against the chunk text and rewrites or blocks wrong ones.

This fixes failure 2, where the RAGAS judge missed the scope error (faithfulness 0.88). It catches the error before the customer sees it. Failure 2 was that the model misstated the return policy, just saying that it was for specific items and not the whole array of products.

Another one would be churn. For churn, it will be a time-based feature, like clickstream and weekly purchase trend, and train on several time windows, not on one cutoff. This targets the weak features like category diversity and channel mix, since they added little. Behavior over time is where the signal lives: customers who are still buying but slowing down. 

