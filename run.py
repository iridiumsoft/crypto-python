import os
from flask import Flask, jsonify
from dotenv import load_dotenv
from flask_cors import CORS, cross_origin

from controllers.trading import api

# New App
app = Flask(__name__)
cors = CORS(app)

# Load Env file to use as configuration
load_dotenv('.env')

# Register Blueprint
app.register_blueprint(api)


# Error handling
@app.errorhandler(404)
def handle_404(error):
    print(error)
    return jsonify(status_code=404, msg="Page not found")


@app.errorhandler(500)
def handle_404(error):
    print(error)
    return jsonify(status_code=500, msg="Something went wrong")


# Start Application
if __name__ == "__main__":
    app.run(debug=os.getenv("DEBUG"))
