from flask import Flask, jsonify
from flask_cors import CORS
from src.m1_priority.routes import m1_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(m1_bp, url_prefix='/api/priority')
# Healthcheck endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "message": "Irrigation Advisory System API running"})

# Member 1, 2, and 3 will import and register their route blueprints here:
# from src.m1_priority.routes import m1_bp
# app.register_blueprint(m1_bp, url_prefix='/api/priority')

if __name__ == '__main__':
    app.run(debug=True, port=5000)