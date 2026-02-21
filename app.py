from flask import Flask, render_template, request

from rag_core import run_query

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    query = ""
    answer = ""
    retrieved = []
    error = ""

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            try:
                retrieved, answer = run_query(query)
            except Exception as exc:
                error = str(exc)
        else:
            error = "Please enter a query."

    return render_template(
        "index.html",
        query=query,
        answer=answer,
        retrieved=retrieved,
        error=error,
    )


@app.route("/check-me-out", methods=["GET"])
def check_me_out():
    return render_template("check_me_out.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
