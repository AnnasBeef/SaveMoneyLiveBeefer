import csv
import json
import re
import subprocess

# ====== CONFIG ======
DATA_PATH = "data/products.csv"   # change to products_enriched_clean.csv if you made it
TOP_K = 8
MODEL_NAME = "llama3.1:8b"  # change if your Ollama model name is different (e.g., "gemma2:9b")
# ====================


def parse_price(price_str: str) -> float | None:
    cleaned = (
        price_str
        .encode("latin1", errors="ignore")
        .decode("utf-8", errors="ignore")
        .replace("£", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_books() -> list[dict]:
    books = []
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            price_num = parse_price(row.get("price", ""))
            if price_num is None:
                continue
            row["_price_num"] = price_num
            books.append(row)
    return books


def has_price_context(query: str) -> bool:
    q = query.lower()
    price_cues = [
        "price", "priced", "cost", "costs", "dollar", "dollars",
        "usd", "gbp", "pound", "pounds", "$", "£", "cheap", "cheapest",
        "expensive", "budget",
    ]
    return any(cue in q for cue in price_cues)


def has_temperature_context(query: str) -> bool:
    q = query.lower()
    temp_cues = ["degree", "degrees", "fahrenheit", "celsius", " f", " c", "°f", "°c"]
    return any(cue in q for cue in temp_cues)


def parse_price_intent(query: str) -> dict | None:
    q = query.lower().strip()
    explicit_price_signal = has_price_context(q)
    if has_temperature_context(q) and not explicit_price_signal:
        return None

    if any(phrase in q for phrase in ["highest price", "most expensive", "priciest", "max price"]):
        return {"type": "highest"}
    if any(phrase in q for phrase in ["lowest price", "cheapest", "least expensive", "min price"]):
        return {"type": "lowest"}

    between_match = re.search(
        r"(?:between|from)\s+\$?(\d+(?:\.\d+)?)\s+(?:and|to)\s+\$?(\d+(?:\.\d+)?)",
        q
    )
    if between_match:
        p1 = float(between_match.group(1))
        p2 = float(between_match.group(2))
        low, high = sorted([p1, p2])
        return {"type": "between", "low": low, "high": high}

    if not explicit_price_signal:
        return None

    comparisons = [
        ("gte", r"(?:>=|at least|no less than|minimum of)\s+\$?(\d+(?:\.\d+)?)"),
        ("lte", r"(?:<=|at most|no more than|maximum of)\s+\$?(\d+(?:\.\d+)?)"),
        ("gt", r"(?:>|over|above|greater than|more than|higher than)\s+\$?(\d+(?:\.\d+)?)"),
        ("lt", r"(?:<|under|below|less than|lower than)\s+\$?(\d+(?:\.\d+)?)"),
        ("eq", r"(?:=|exactly|equal to)\s+\$?(\d+(?:\.\d+)?)"),
    ]

    for op, pattern in comparisons:
        match = re.search(pattern, q)
        if match:
            return {"type": op, "value": float(match.group(1))}

    return None


def solve_price_query(query: str, books: list[dict]) -> dict | None:
    intent = parse_price_intent(query)
    if intent is None:
        return None

    intent_type = intent["type"]

    if intent_type == "highest":
        chosen = max(books, key=lambda b: (b["_price_num"], b.get("title", "")))
        return {"kind": "single", "items": [chosen], "label": "Highest-priced book"}

    if intent_type == "lowest":
        chosen = min(books, key=lambda b: (b["_price_num"], b.get("title", "")))
        return {"kind": "single", "items": [chosen], "label": "Lowest-priced book"}

    if intent_type == "between":
        low = intent["low"]
        high = intent["high"]
        items = [b for b in books if low <= b["_price_num"] <= high]
        items.sort(key=lambda b: (b["_price_num"], b.get("title", "")))
        return {"kind": "list", "items": items, "label": f"Books priced between £{low:.2f} and £{high:.2f}"}

    value = intent["value"]
    if intent_type == "gt":
        items = [b for b in books if b["_price_num"] > value]
        label = f"Books priced above £{value:.2f}"
    elif intent_type == "gte":
        items = [b for b in books if b["_price_num"] >= value]
        label = f"Books priced at least £{value:.2f}"
    elif intent_type == "lt":
        items = [b for b in books if b["_price_num"] < value]
        label = f"Books priced below £{value:.2f}"
    elif intent_type == "lte":
        items = [b for b in books if b["_price_num"] <= value]
        label = f"Books priced at most £{value:.2f}"
    else:
        items = [b for b in books if abs(b["_price_num"] - value) < 1e-9]
        label = f"Books priced exactly £{value:.2f}"

    items.sort(key=lambda b: (b["_price_num"], b.get("title", "")))
    return {"kind": "list", "items": items, "label": label}


def print_price_answer(result: dict) -> None:
    items = result["items"]
    label = result["label"]
    print(f"\n{label}:")

    if not items:
        print("No matching books found.\n")
        return

    if result["kind"] == "single":
        b = items[0]
        price = b.get("price", "").replace("Â£", "£")
        print(f"- {b.get('title', '')} ({price}) | {b.get('category', '')}\n")
        return

    print(f"Found {len(items)} match(es).")
    for b in items[:20]:
        print(f"- {b.get('title', '')} | £{b['_price_num']:.2f} | {b.get('category', '')}")
    if len(items) > 20:
        print(f"...and {len(items) - 20} more.")
    print()


def retrieve_books(query: str, max_price: float | None = None, top_k: int = TOP_K) -> list[dict]:
    """
    Mini-RAG retrieval (local):
    - tokenizes query into words (len >= 3)
    - scores rows by keyword matches across title/category/tags/summary/description
    - boosts matches in tags/category/title
    - optional price filter: "under <number>"
    """
    q = query.lower()
    q_words = [w for w in re.findall(r"[a-zA-Z]+", q) if len(w) >= 3]

    results = []
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").lower()
            category = row.get("category", "").lower()
            tags = row.get("llm_tags", "").lower()
            summary = row.get("llm_summary", "").lower()
            desc = row.get("description", "").lower()

            # Base keyword match across all text
            haystack = " ".join([title, category, tags, summary, desc])
            base_score = sum(1 for w in q_words if w in haystack)

            # Field boosts (makes retrieval smarter)
            category_boost = 2 * sum(1 for w in q_words if w in category)
            tag_boost = 3 * sum(1 for w in q_words if w in tags)
            title_boost = 2 * sum(1 for w in q_words if w in title)

            score = base_score + category_boost + tag_boost + title_boost
            if score == 0:
                continue

            # Optional price filter
            if max_price is not None:
                price_num = parse_price(row.get("price", ""))
                if price_num is None or price_num > max_price:
                    continue

            row["_score"] = score
            results.append(row)

    results.sort(key=lambda r: r["_score"], reverse=True)
    return results[:top_k]


def wants_json_output(query: str) -> bool:
    q = query.lower()
    return "json" in q or "valid json" in q


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def generate_answer(query: str, retrieved: list[dict], json_mode: bool = False) -> str:
    """
    Mini-RAG generation (LOCAL):
    - builds compact context from retrieved rows
    - calls local LLM via: ollama run <MODEL_NAME>
    """
    context_lines = []
    for i, b in enumerate(retrieved, start=1):
        context_lines.append(
            f"{i}. Title: {b.get('title','')}\n"
            f"   Price: {b.get('price','')}\n"
            f"   Category: {b.get('category','')}\n"
            f"   Tags: {b.get('llm_tags','')}\n"
            f"   Summary: {b.get('llm_summary','')}\n"
        )

    context = "\n".join(context_lines)

    if json_mode:
        prompt = f"""You are an assistant that answers using ONLY the provided BOOK CONTEXT.
Return ONLY valid JSON (no markdown, no prose) with this exact schema:
{{
  "answer": "string",
  "matches": [
    {{
      "title": "string",
      "reason": "string",
      "evidence_field": "category|tags|summary|description",
      "confidence": "high|medium|low"
    }}
  ],
  "insufficient_context": true
}}
Set "insufficient_context" to false only if matches clearly support the answer.
Do not invent books that are not in context.

USER QUESTION:
{query}

BOOK CONTEXT:
{context}
"""
    else:
        prompt = f"""You are an assistant that answers questions using ONLY the provided book context.
Do not invent books that are not listed. If the context is insufficient, say so and suggest better keywords.

USER QUESTION:
{query}

BOOK CONTEXT:
{context}

INSTRUCTIONS:
- Recommend up to 5 books max (if applicable).
- Use bullet points.
- For each item, include the title and a 1-line reason grounded in the context.
"""

    result = subprocess.run(
        ["ollama", "run", MODEL_NAME],
        input=prompt,
        text=True,
        capture_output=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Ollama call failed.\nSTDERR:\n{result.stderr}\n\n"
            f"Tip: make sure Ollama is installed and MODEL_NAME exists: {MODEL_NAME}"
        )

    output = result.stdout.strip()

    if not json_mode:
        return output

    parsed = _extract_json_object(output)
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    fallback = {
        "answer": "Could not produce reliable structured output from the retrieved context.",
        "matches": [],
        "insufficient_context": True,
    }
    return json.dumps(fallback, ensure_ascii=False, indent=2)


def main():
    print("\nMini RAG Q&A (LOCAL) (type 'quit' to exit)")
    print("Examples:")
    print(" - poetry humor under 60")
    print(" - historical fiction lgbtq")
    print(" - books about identity and performance\n")

    while True:
        query = input("Query> ").strip()
        if query.lower() in {"quit", "exit"}:
            break

        books = load_books()
        price_result = solve_price_query(query, books)
        if price_result is not None:
            print_price_answer(price_result)
            continue

        # Detect price filter like: "under 60"
        max_price = None
        m = re.search(r"under\s+(\d+(\.\d+)?)", query.lower())
        if m:
            if has_price_context(query) and not has_temperature_context(query):
                max_price = float(m.group(1))

        retrieved = retrieve_books(query, max_price=max_price)

        # Debug: show what got retrieved
        print("\nRetrieved titles:")
        for b in retrieved:
            price_display = b.get("price", "").replace("Â£", "£")
            print("-", b.get("title", ""), "|", b.get("category", ""), "|", price_display, "| score:", b.get("_score"))
        print()


        if not retrieved:
            print("No matches found. Try different keywords.\n")
            continue

        json_mode = wants_json_output(query)
        answer = generate_answer(query, retrieved, json_mode=json_mode)
        print("\n" + answer + "\n")


if __name__ == "__main__":
    main()
