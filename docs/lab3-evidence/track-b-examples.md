# Track B — Input/output examples and failure cases

Pipeline: section-level chunks (29) of `northstar-policy-docs/` with contextual headers → Titan Text Embeddings V2 (1024-d, normalized) → FAISS `IndexFlatIP` (cosine) → top K=4 → Claude Haiku 4.5 (`us.` inference profile, temperature 0.2). Baseline runs use one tier query; `multiquery` runs use three queries per customer (tier benefits / channel-specific returns+shipping / categories) merged round-robin, still K=4. Judge: `us.anthropic.claude-haiku-4-5-20251001-v1:0`. Full scores: [`rag_eval.csv`](rag_eval.csv).

Chunk IDs are `<document>-<n>`, where n is the section number (e.g. `POL-LOY-011-4` = Loyalty terms §4 Tier Benefits, `POL-RET-004-4` = Returns §4 Non-returnable merchandise).

## Correct behavior (5)

### 1. Gold, online, Outdoor/Footwear

- **Run:** `multiquery-run1` · **Customer:** `CUST-10000317`
- **Customer profile (raw):** churn_probability=0.81, loyalty_tier=Gold, days_since_last_purchase=47, total_lifetime_value=3120.4, avg_order_value=186.25, category_diversity_score=0.5, online_to_store_ratio=0.72, top_categories=['Outdoor', 'Footwear']
- **Profile as the model saw it:** Customer profile: Gold member; buys mostly Outdoor and Footwear; shops in a few categories; shops mostly online; hasn't bought in over a month; high churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-SHP-007-2`, `POL-RET-004-4`, `POL-LOY-011-2`
- **RAGAS:** faithfulness 0.60 · answer relevancy 0.33 · context recall 1.00

**Generated offer:**
> As a Gold member, you currently enjoy free standard shipping on every order and free return shipping on outdoor gear and footwear—making it easier to find your perfect fit without worrying about costs. Earn 1.5× points on your next purchase in these categories and take advantage of your 30-day return window to shop with confidence.

**Why this is correct behavior:** It did not hallucinate. Every benefit comes from the policy (`POL-LOY-011-4`: free standard shipping always, free return shipping, 1.5× points, 30-day window), and it did not promise the Platinum 60-day window or free expedited shipping. It also turns his shopping into a points opportunity. Small caveat: "free return shipping on outdoor gear and footwear" ties a store-wide benefit to his categories, the same scope issue as Failure 2.

### 2. Bronze, in store, Apparel only

- **Run:** `multiquery-run2` · **Customer:** `CUST-10000904`
- **Customer profile (raw):** churn_probability=0.74, loyalty_tier=Bronze, days_since_last_purchase=68, total_lifetime_value=312.8, avg_order_value=41.15, category_diversity_score=0.125, online_to_store_ratio=0.2, top_categories=['Apparel']
- **Profile as the model saw it:** Customer profile: Bronze member; buys mostly Apparel; shops in one category; shops mostly in store (shipping perks matter less); hasn't bought in over a month; high churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-RET-004-6`, `POL-RET-004-4`, `POL-LOY-011-3`
- **RAGAS:** faithfulness 0.50 · answer relevancy 0.46 · context recall 0.40

**Generated offer:**
> Come back to Apparel and earn 1 point per $1 spent—your points are valuable and expire 18 months from your last purchase, so don't let them disappear. As a Bronze member, you can return items in store immediately at any of our 400 locations, making it easy to find exactly what works for you.

**Why this is correct behavior:** These claims are correct on the offer. We can see it offers 1 point per $1 spent (`POL-LOY-011-3`). The claim that points expire 18 months after the last purchase is true (`POL-LOY-011-3`). It prompts and encourages the customer, letting them go away, and also states the return policies for the Bronze member are correct. 

### 3. Platinum, high value, broad categories

- **Run:** `multiquery-run2` · **Customer:** `CUST-10000122`
- **Customer profile (raw):** churn_probability=0.66, loyalty_tier=Platinum, days_since_last_purchase=39, total_lifetime_value=8940.0, avg_order_value=447.0, category_diversity_score=0.75, online_to_store_ratio=0.55, top_categories=['Outdoor', 'Electronics', 'Home']
- **Profile as the model saw it:** Customer profile: Platinum member; buys mostly Outdoor and Electronics and Home; shops across many categories; shops both online and in store; hasn't bought in over a month; moderate churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-RET-004-6`, `POL-RET-004-4`, `POL-LOY-011-2`
- **RAGAS:** faithfulness 0.38 · answer relevancy 0.36 · context recall 0.33

**Generated offer:**
> As a Platinum member, you currently earn 2× points on every purchase and enjoy unlimited free gear repair across Outdoor and Electronics categories—plus you have 60 days to return items, giving you extra flexibility on your orders. Your $100 annual gear credit is waiting to be used on the gear you love most, whether it's outdoor equipment, home essentials, or electronics.

**Why this is correct behavior:** What I like about this is that it recognizes the shopping habits of the customer. In this case, we know that the customer mostly spends on outdoors, and the RAG system recognizes it and encourages him to use his current promotion as a platinum member with 100 annual gear credit. This customer is not super high churn since it's 0.66, but still, the RAG system makes a good offer, in my opinion. 

### 4. Silver, just under the Gold threshold (near-threshold framing)

- **Run:** `multiquery-run2` · **Customer:** `CUST-10000588`
- **Customer profile (raw):** churn_probability=0.7, loyalty_tier=Silver, total_lifetime_value=1985.0, days_since_last_purchase=52, avg_order_value=132.3, category_diversity_score=0.375, online_to_store_ratio=0.61, top_categories=['Home', 'Beauty']
- **Profile as the model saw it:** Customer profile: Silver member; buys mostly Home and Beauty; shops in a few categories; shops mostly online; hasn't bought in over a month; high churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-SHP-007-2`, `POL-RET-004-4`, `POL-LOY-011-2`
- **RAGAS:** faithfulness 0.57 · answer relevancy 0.35 · context recall 0.50

**Generated offer:**
> As a Silver member, you currently earn 1.25× points on every purchase and get free standard shipping on orders over $50—benefits that add up fast on your Home and Beauty favorites. Your next order in these categories could be the start of building toward Gold status, where you'd unlock free returns and 24-hour early access to our sales. Shop now and watch your rewards grow.

**Why this is correct behavior:** What I love about this offer is that, without providing exact numbers, it lets the customer know that he's close to reaching a higher tier. It makes a subtle comment that encourages the customer to keep purchasing to get more benefits. It states the current benefit that this person has: 1.25 per purchase, free standard shipping over $50 (`POL-LOY-011-4`), and things like that. I think this is a really good offer. 

### 5. Silver, only Silver benefits

- **Run:** `multiquery-run1` · **Customer:** `CUST-10000588`
- **Customer profile (raw):** churn_probability=0.7, loyalty_tier=Silver, total_lifetime_value=1985.0, days_since_last_purchase=52, avg_order_value=132.3, category_diversity_score=0.375, online_to_store_ratio=0.61, top_categories=['Home', 'Beauty']
- **Profile as the model saw it:** Customer profile: Silver member; buys mostly Home and Beauty; shops in a few categories; shops mostly online; hasn't bought in over a month; high churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-SHP-007-2`, `POL-RET-004-4`, `POL-LOY-011-2`
- **RAGAS:** faithfulness 0.60 · answer relevancy 0.40 · context recall 0.50

**Generated offer:**
> As a Silver member, you currently earn 1.25× points on every purchase and get free standard shipping on orders over $50—benefits that add up fast on your Home and Beauty favorites. Your next order in these categories is a great opportunity to stack those rewards toward your goals. Shop now and watch your points grow with every purchase.

**Why this is correct behavior:** I think this is the same thing as the previous offers. It's still the same: Silver member, same benefits as before. I think it's shorter than the other offers, but it also just focuses on the top categories of the customer: Home and Beauty. It recognizes that and goes for an offer or for retention sentence, and it's not making up things. 

## Failure cases (2)

### Failure 1: invented urgency and terms

- **Run:** `baseline-run2` · **Customer:** `CUST-10000588`
- **Customer profile (raw):** churn_probability=0.7, loyalty_tier=Silver, total_lifetime_value=1985.0, days_since_last_purchase=52, avg_order_value=132.3, category_diversity_score=0.375, online_to_store_ratio=0.61, top_categories=['Home', 'Beauty']
- **Profile as the model saw it:** Customer profile: Silver member; buys mostly Home and Beauty; shops in a few categories; shops mostly online; hasn't bought in over a month; high churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-LOY-011-2`, `POL-LOY-011-5`, `POL-SHP-007-2`
- **RAGAS:** faithfulness 0.33 · answer relevancy 0.41 · context recall 0.75

**Generated offer:**
> As a Silver member, you currently earn 1.25× points on every purchase and get free standard shipping on orders over $50. Come back to Home and Beauty this week and enjoy these rewards on us—your points and shipping benefits are waiting.

**What went wrong:** The tier benefits are right, but the offer adds things that are not in any retrieved chunk: "this week" (a made-up deadline) and "enjoy these rewards on us" (sounds like a free gift that does not exist). Those are invented claims, and each one counts against faithfulness.

**Root cause:** I think the prompt was not clear enough about avoiding urgency and extra promises, so the model fell back on normal marketing habits.

**Proposed fix:** Make the prompt stricter so it removes those urgency words and terms.

### Failure 2: a benefit described with the wrong scope / mechanism

- **Run:** `baseline-run1` · **Customer:** `CUST-10000122`
- **Customer profile (raw):** churn_probability=0.66, loyalty_tier=Platinum, days_since_last_purchase=39, total_lifetime_value=8940.0, avg_order_value=447.0, category_diversity_score=0.75, online_to_store_ratio=0.55, top_categories=['Outdoor', 'Electronics', 'Home']
- **Profile as the model saw it:** Customer profile: Platinum member; buys mostly Outdoor and Electronics and Home; shops across many categories; shops both online and in store; hasn't bought in over a month; moderate churn risk
- **Retrieved chunk IDs:** `POL-LOY-011-4`, `POL-LOY-011-2`, `POL-SHP-007-2`, `POL-LOY-011-5`
- **RAGAS:** faithfulness 0.89 · answer relevancy 0.34 · context recall 0.33

**Generated offer:**
> As a Platinum member, you currently earn 2× points on every purchase and get free standard shipping on any order—plus you have 60 days to return items from Outdoor, Electronics, and Home categories. Come back and shop this week to make the most of your $100 annual gear credit before the year ends, and enjoy 48-hour early access to our upcoming sales.

**What went wrong:** Most of the offer is right, but it has a subtle error: "you have 60 days to return items from Outdoor, Electronics, and Home categories." This can be read as the 60-day window applying only to those categories, so the customer could think that a product from a different category has a shorter return window, or none at all. The policy (POL-RET-004 §1.1) gives Platinum 60 days on all eligible merchandise.

**Root cause:** The model tried to personalize the offer as much as it could and fell into this trap: it took the customer's top categories from the profile and attached them to a benefit.

**Proposed fix:** Add a prompt rule: "Benefits apply store-wide. Mention a category only as a product suggestion, never as a condition of a benefit." The point is that the model should not make assumptions about a benefit's scope; the scope should come from what the RAG system retrieves.

