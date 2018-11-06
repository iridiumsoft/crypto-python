from flask import Blueprint, request, g, jsonify

api = Blueprint('api', __name__, url_prefix='/')


@api.route('/', methods=['GET'])
def get_orders():
    return "Hello from orders"
