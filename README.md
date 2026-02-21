# SaveMoneyLiveBeefer (Local UI)

This project includes a local Flask website UI for querying your RAG pipeline over book CSV data.
All generation is local-only via Ollama.

## 1) Setup virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2) Start Ollama and pull model

```bash
ollama serve
```

In another terminal:

```bash
ollama pull llama3.1:8b
```

## 3) Run the web app

```bash
python app.py
```

Open `http://localhost:5000`.

## Notes

- App title: `SaveMoneyLiveBeefer`
- Default dataset:
  - `data/products_enriched.csv` if present
  - otherwise `data/products.csv`
- This app is local-only and uses local Ollama inference.
