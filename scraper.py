import requests
from bs4 import BeautifulSoup
import csv
from urllib.parse import urljoin

base_url = "http://books.toscrape.com/"

response = requests.get(base_url)
soup = BeautifulSoup(response.text, "html.parser")

books = soup.find_all("article", class_="product_pod")

with open("data/products.csv", mode="w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerow(["title", "price", "rating", "category", "description"])

    for book in books:
        title = book.h3.a["title"]
        price = book.find("p", class_="price_color").text
        rating = book.find("p", class_="star-rating")["class"][1]

        # Fix URL properly
        book_link = book.h3.a["href"]
        book_url = urljoin(base_url, book_link)

        book_response = requests.get(book_url)
        book_soup = BeautifulSoup(book_response.text, "html.parser")

        # SAFE category extraction
        breadcrumb = book_soup.find("ul", class_="breadcrumb")
        if breadcrumb:
            category = breadcrumb.find_all("li")[2].text.strip()
        else:
            category = "Unknown"

        # SAFE description extraction
        description_tag = book_soup.find("div", id="product_description")
        if description_tag:
            description = description_tag.find_next_sibling("p").text
        else:
            description = "No description available"

        writer.writerow([title, price, rating, category, description])

print("Full scraping complete.")

