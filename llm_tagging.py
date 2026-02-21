import csv
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://books.toscrape.com/"
START_PAGE = "catalogue/page-1.html"

OUTPUT_PATH = "data/products.csv"
DELAY_SECONDS = 0  # polite delay between requests


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    # Force correct decoding (prevents weird Â£ issues)
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def parse_rating(book_soup: BeautifulSoup) -> str:
    tag = book_soup.find("p", class_="star-rating")
    if not tag or "class" not in tag.attrs:
        return "Unknown"
    # Example: ["star-rating", "Three"]
    classes = tag["class"]
    return classes[1] if len(classes) > 1 else "Unknown"


def parse_category(book_soup: BeautifulSoup) -> str:
    breadcrumb = book_soup.find("ul", class_="breadcrumb")
    if not breadcrumb:
        return "Unknown"
    items = breadcrumb.find_all("li")
    # Typically: Home > Books > Category > Title
    return items[2].get_text(strip=True) if len(items) >= 3 else "Unknown"


def parse_description(book_soup: BeautifulSoup) -> str:
    desc_header = book_soup.find("div", id="product_description")
    if not desc_header:
        return "No description available"
    p = desc_header.find_next_sibling("p")
    return p.get_text(" ", strip=True) if p else "No description available"


def parse_price(book_soup: BeautifulSoup) -> str:
    price_tag = book_soup.find("p", class_="price_color")
    return price_tag.get_text(strip=True) if price_tag else ""


def parse_title(book_soup: BeautifulSoup) -> str:
    h1 = book_soup.find("div", class_="product_main")
    if not h1:
        return ""
    title_tag = h1.find("h1")
    return title_tag.get_text(strip=True) if title_tag else ""


def parse_book_detail(book_url: str) -> dict:
    soup = get_soup(book_url)

    return {
        "title": parse_title(soup),
        "price": parse_price(soup),
        "rating": parse_rating(soup),
        "category": parse_category(soup),
        "description": parse_description(soup),
        "url": book_url,
    }


def get_book_urls_from_listing(listing_url: str) -> list[str]:
    soup = get_soup(listing_url)
    urls = []

    for article in soup.select("article.product_pod h3 a"):
        rel = article.get("href", "")
        # Listing pages have links like "../../../a-book/index.html"
        book_url = urljoin(listing_url, rel)
        urls.append(book_url)

    return urls


def get_next_page_url(listing_url: str) -> str | None:
    soup = get_soup(listing_url)
    next_li = soup.select_one("li.next a")
    if not next_li:
        return None
    rel = next_li.get("href", "")
    return urljoin(listing_url, rel)


def main():
    # Start from page 1
    current_listing = urljoin(BASE_URL, START_PAGE)

    all_book_urls = []
    page_count = 0

    print("Collecting all listing pages + book URLs...")

    while current_listing:
        page_count += 1
        print(f"Listing page {page_count}: {current_listing}")

        book_urls = get_book_urls_from_listing(current_listing)
        all_book_urls.extend(book_urls)

        current_listing = get_next_page_url(current_listing)
        time.sleep(DELAY_SECONDS)

    # Deduplicate (just in case)
    all_book_urls = list(dict.fromkeys(all_book_urls))
    print(f"\nFound {len(all_book_urls)} unique book URLs.\n")

    # Write CSV
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["title", "price", "rating", "category", "description", "url"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, book_url in enumerate(all_book_urls, start=1):
            try:
                book = parse_book_detail(book_url)
                writer.writerow(book)

                if i % 50 == 0:
                    print(f"Scraped {i}/{len(all_book_urls)} books...")
            except Exception as e:
                print(f"Failed book {i}: {book_url} -> {e}")

            time.sleep(DELAY_SECONDS)

    print(f"\nDone. Saved full dataset to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
