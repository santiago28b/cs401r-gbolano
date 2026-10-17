import json, os, numpy as np, faiss, boto3
from rag.ingest import embed           # works once the test lines are gone

MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
brt = boto3.client("bedrock-runtime", region_name="us-east-1")

index = faiss.read_index("rag/index/policies.faiss")
chunks = json.load(open("rag/index/chunks.json"))
K = 4                                 

def retrieve(query, k=K):
    q = embed(query).reshape(1, -1)
    scores, ids = index.search(q, k)
    return [chunks[i] for i in ids[0]]


# Retrieval mode: "single" = one tier query (baseline runs), "multi" = one query
# per need, merged round-robin (the measured improvement). Total stays K either way,
# so the before/after compares better chunks, not more chunks.
RETRIEVAL_MODE = os.environ.get("RAG_RETRIEVAL", "multi")


def build_queries(c):
    """One query per thing the offer needs: tier benefits, how they shop, what they buy."""
    tier = c.get("loyalty_tier", "")
    cats = " and ".join(c.get("top_categories", []))
    online = c.get("online_to_store_ratio", 0.5) >= 0.6
    if online:
        channel = f"{tier} free return shipping cost, return window, standard shipping threshold for online orders"
    else:
        channel = f"{tier} in-store returns, store pickup, return shipping cost for returns by mail"
    return [
        f"{tier} tier benefits points earn rate birthday reward early access",
        channel,
        f"{cats} merchandise: final sale items, oversized items, gear repair, category exclusions",
    ]


def retrieve_multi(queries, k=K, per_query=3):
    """Round-robin merge: 1st hit of each query, then 2nd of each..., no duplicates, stop at k."""
    ranked = [retrieve(q, per_query) for q in queries]
    out, seen = [], set()
    for rank in range(per_query):
        for hits in ranked:
            h = hits[rank]
            if h["id"] not in seen:
                out.append(h)
                seen.add(h["id"])
            if len(out) == k:
                return out
    return out

def profile_text(c):
    # Weakness #2 fix: turn raw numbers into meaning the model can use
    # e.g. category_diversity_score 0.13 -> "shops in a single category"
    #      online_to_store_ratio 0.72  -> "shops mostly online"
    parts = []
    loyalty_tier = c.get("loyalty_tier")
    if loyalty_tier:
        parts.append(f"{loyalty_tier} member")

    top_categories = c.get("top_categories")
    if top_categories:
        parts.append(f"buys mostly {' and '.join(top_categories)}")

    category_diversity_score = c.get("category_diversity_score")
    if category_diversity_score is not None:
        if category_diversity_score < 0.3:
            parts.append("shops in one category")
        elif category_diversity_score <= 0.6:
            parts.append("shops in a few categories")
        else:
            parts.append("shops across many categories")

    online_to_store_ratio = c.get("online_to_store_ratio")
    if online_to_store_ratio is not None:
        if online_to_store_ratio >= 0.6:
            parts.append("shops mostly online")
        elif online_to_store_ratio > 0.4:
            parts.append("shops both online and in store")
        else:
            parts.append("shops mostly in store (shipping perks matter less)")

    days_since_last_purchase = c.get("days_since_last_purchase")
    if days_since_last_purchase is not None:
        if days_since_last_purchase < 30:
            parts.append("bought recently")
        elif days_since_last_purchase <= 90:
            parts.append("hasn't bought in over a month")
        else:
            parts.append("hasn't bought in over 3 months")

    churn_probability = c.get("churn_probability")
    if churn_probability is not None:
        if churn_probability >= 0.7:
            parts.append("high churn risk")
        elif churn_probability >= 0.4:
            parts.append("moderate churn risk")
        else:
            parts.append("low churn risk")

    return "; ".join(parts)

SYSTEM_PROMPT =  """You are a NorthStar retention marketing writer. Write a retention offer directly to the customer.

Rules:
- Write a 2-3 sentence retention offer with one specific product category
- Use only benefits that the policy excerpts give this customer's tier. Never a higher tier's
- Phrase tier benefits conditionally. example: "As a [tier] member, you currently..."
- Never state the tier as guaranteed fact. The tier in the profile is an estimate and may not match the policy tier
- No made up deadlines, codes or percentages that aren't in the excerpts. No warm up lines like 'we missed you'
- Never promise a return on final sale items, never free expedited shipping
- Never give the churn score or internal scores to the customer
- Output only the offer text. No subject line, greeting or sign-off
"""
# Your rules. Weakness #1 fix goes here: the model gets the tier and must only
# use benefits that the retrieved policy text gives that tier.
# Ideas: 2-3 sentences, one specific category, no invented terms or deadlines,
# no warm-up lines, tier benefits stated conditionally ("as a Gold member, you currently...")

def generate_offer(customer_context, question):
    tier = customer_context.get("loyalty_tier", "")
    query = f"{tier} tier benefits, retention offers for at-risk members, free shipping threshold"
    if RETRIEVAL_MODE == "single":
        hits = retrieve(query)
    else:
        hits = retrieve_multi(build_queries(customer_context))
    profile = "Customer profile: " + profile_text(customer_context)
    user_prompt = f"{profile}\n\nPolicy excerpts:\n" + "\n\n".join(
        f"[{h['id']}]\n{h['text']}" for h in hits) + f"\n\nTask: {question}"

    resp = brt.converse(
        modelId=MODEL,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 300},
    )
    answer = resp["output"]["message"]["content"][0]["text"]
    return {"answer": answer, "contexts": [profile] + [h["text"] for h in hits],
            "chunk_ids": [h["id"] for h in hits]}