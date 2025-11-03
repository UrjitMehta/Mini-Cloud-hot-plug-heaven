from flask import Flask, jsonify
import psutil

app = Flask(__name__)

@app.route("/usage")
def usage():
    return jsonify({"cpu": psutil.cpu_percent(interval=1)})

if __name__ == "__main__":
    print("CPU Agent running on port 5000 (VM side)")
    app.run(host="0.0.0.0", port=5000)
