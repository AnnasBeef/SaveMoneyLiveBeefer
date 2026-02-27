import csv
import os
import re
import subprocess
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

TOP_K = 8
MODEL_NAME = "llama3.1:8b"
IMAGE_FETCH_TIMEOUT = 6

_TITLE_TO_URL: dict[str, str] | None = None
_IMAGE_URL_CACHE: dict[str, str] = {}


def default_data_path() -> str:
    enriched = "data/products_enriched.csv"
    base = "data/products.csv"
    return enriched if os.path.exists(enriched) else base


def _load_title_url_lookup() -> dict[str, str]:
    global _TITLE_TO_URL
    if _TITLE_TO_URL is not None:
        return _TITLE_TO_URL

    path = "data/products.csv"
    lookup: dict[str, str] = {}
    if not os.path.exists(path):
        _TITLE_TO_URL = lookup
        return lookup

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title", "") or "").strip()
            url = (row.get("url", "") or "").strip()
            if title and url:
                lookup[title] = url

    _TITLE_TO_URL = lookup
    return lookup


def clean_price_text(price_str: str) -> str:
    return (price_str or "").replace("Â£", "£").strip()


def parse_price(price_str: str) -> float | None:
    cleaned = (
        clean_price_text(price_str)
        .replace("£", "")
        .replace("$", "")
        .replace(",", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_books(data_path: str | None = None) -> list[dict]:
    path = data_path or default_data_path()
    books: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["price"] = clean_price_text(row.get("price", ""))
            price_num = parse_price(row.get("price", ""))
            if price_num is None:
                continue
            row["_price_num"] = price_num
            if not row.get("url"):
                row["url"] = _load_title_url_lookup().get(row.get("title", ""), "")
            books.append(row)
    return books


def fetch_cover_image_url(book_url: str) -> str:
    if not book_url:
        return ""
    if book_url in _IMAGE_URL_CACHE:
        return _IMAGE_URL_CACHE[book_url]

    try:
        resp = requests.get(book_url, timeout=IMAGE_FETCH_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        img = soup.select_one("article.product_page div.item img")
        if img and img.get("src"):
            image_url = urljoin(book_url, img["src"])
            _IMAGE_URL_CACHE[book_url] = image_url
            return image_url
    except Exception:
        pass

    _IMAGE_URL_CACHE[book_url] = ""
    return ""


def retrieve_books(query: str, top_k: int = TOP_K, data_path: str | None = None) -> list[dict]:
    q = query.lower()
    q_words = [w for w in re.findall(r"[a-zA-Z]+", q) if len(w) >= 3]

    results: list[dict] = []
    for row in load_books(data_path):
        title = row.get("title", "").lower()
        category = row.get("category", "").lower()
        tags = row.get("llm_tags", "").lower()
        summary = row.get("llm_summary", "").lower()
        desc = row.get("description", "").lower()

        haystack = " ".join([title, category, tags, summary, desc])
        base_score = sum(1 for w in q_words if w in haystack)
        category_boost = 2 * sum(1 for w in q_words if w in category)
        tag_boost = 3 * sum(1 for w in q_words if w in tags)
        title_boost = 2 * sum(1 for w in q_words if w in title)
        score = base_score + category_boost + tag_boost + title_boost

        if score == 0:
            continue

        row["_score"] = score
        results.append(row)

    results.sort(key=lambda r: r["_score"], reverse=True)
    top_results = results[:top_k]
    for row in top_results:
        row["_image_url"] = fetch_cover_image_url(row.get("url", ""))
    return top_results


def generate_answer(query: str, retrieved: list[dict]) -> str:
    if not retrieved:
        return "No matches found in the dataset. Try adding clearer topic keywords."

    context_lines = []
    for i, b in enumerate(retrieved, start=1):
        context_lines.append(
            f"{i}. Title: {b.get('title', '')}\n"
            f"   Price: {clean_price_text(b.get('price', ''))}\n"
            f"   Category: {b.get('category', '')}\n"
            f"   Tags: {b.get('llm_tags', '')}\n"
            f"   Summary: {b.get('llm_summary', '')}\n"
        )
    context = "\n".join(context_lines)

    prompt = f"""You are an assistant that answers questions using ONLY the provided book context.
Do not invent books that are not listed. If the context is insufficient, say so.

USER QUESTION:
{query}

BOOK CONTEXT:
{context}

INSTRUCTIONS:
- Recommend at least 1 book.
- Recommend up to 5 books max.
- Use bullet points.
- For each item, include title and a 1-line reason grounded in context.
"""

    result = subprocess.run(
        ["ollama", "run", MODEL_NAME],
        input=prompt,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Ollama call failed.\nSTDERR:\n{result.stderr}\n\n"
            f"Tip: make sure Ollama is installed and model exists: {MODEL_NAME}"
        )

    return result.stdout.strip()


def run_query(query: str) -> tuple[list[dict], str]:
    retrieved = retrieve_books(query)
    answer = generate_answer(query, retrieved)
    return retrieved, answer
