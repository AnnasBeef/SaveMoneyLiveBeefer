import csv

in_path = "data/products_enriched.csv"
out_path = "data/products_enriched_clean.csv"

with open(in_path, newline="", encoding="utf-8") as infile, \
     open(out_path, "w", newline="", encoding="utf-8") as outfile:

    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
    writer.writeheader()

    for row in reader:
        row["price"] = row["price"].replace("Â£", "£").strip()
        writer.writerow(row)

print(f"Cleaned currency. Saved: {out_path}")
