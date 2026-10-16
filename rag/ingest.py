import json, glob, os, re
import numpy as np, faiss

import boto3, json, numpy as np
brt = boto3.client("bedrock-runtime", region_name="us-east-1")

def embed(text: str) -> np.ndarray:
    resp = brt.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
    )
    return np.array(json.loads(resp["body"].read())["embedding"], dtype="float32")


DOCS = "northstar-policy-docs/*.md"
OUT = "rag/index"

def chunk_doc(path):
    text = open(path).read()
    doc_id = re.search(r"\*\*Document ID:\*\*\s*(\S+)", text).group(1)   # e.g. POL-RET-004
    title = re.search(r"^# (.+)$", text, re.M).group(1)                  # first line of the doc
    # every chunk starts with its source so it stands alone (search + LLM both see it)
    prefix = f"{title} ({doc_id})"
    note = re.search(r"\*\*Note:\*\*\s*(.+)", text)                       # only the FAQ has one
    if note:
        prefix += f"\nNote: {note.group(1)}"
    chunks = []
    # split on lines that are only "---" (table rows like |---|---| contain "---" too)
    pieces = [p.strip() for p in text.split("\n---\n")]
    # keep only real sections; drops empty pieces and the title/metadata header
    pieces = [p for p in pieces if p.startswith("## ")]
    for n, piece in enumerate(pieces, start=1):
        chunks.append({"id": f"{doc_id}-{n}", "doc": doc_id, "text": f"{prefix}\n\n{piece}"})
    return chunks

def build_index():
    chunks = [c for p in sorted(glob.glob(DOCS)) for c in chunk_doc(p)]
    print(len(chunks), "chunks")
    vecs = np.vstack([embed(c["text"]) for c in chunks])
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    os.makedirs(OUT, exist_ok=True)
    faiss.write_index(index, f"{OUT}/policies.faiss")
    json.dump(chunks, open(f"{OUT}/chunks.json", "w"), indent=2)

if __name__ == "__main__":
    build_index()