from flask import Flask, render_template, request, jsonify
import json, os, time

app = Flask(__name__)
DATA_FILE = "data.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "cpu_usage": 0,
            "cpu_count": 1,
            "allocations": {},
            "timestamp": time.strftime("%H:%M:%S")
        }, f, indent=2)

def read_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def write_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/")
def index():
    return render_template("dashboard.html", **read_data())

@app.route("/update", methods=["POST"])
def update():
    data = request.json or {}
    payload = {
        "cpu_usage": data.get("cpu_usage", 0),
        "cpu_count": data.get("cpu_count", 1),
        "allocations": data.get("allocations", {}),
        "timestamp": time.strftime("%H:%M:%S")
    }
    write_data(payload)
    return jsonify({"status": "ok"})

@app.route("/data")
def data():
    return jsonify(read_data())

if __name__ == "__main__":
    print("Dashboard running at http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050)
