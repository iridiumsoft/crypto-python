from functools import wraps
import base64
from flask import g, request, url_for, jsonify

from db import db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed = False
        user = {}
        token = request.headers.get("t")
        if token:
            token = token.encode("utf-8")
            try:
                token = base64.b64decode(token)
                token = str(token, 'utf-8')
                token_parts = token.split('-')
                if token_parts[1] is not None:
                    user = db.users.find_one(
                        {'user_name': token_parts[1]},  # Where Clause
                        {'_id': 0, 'user_name': 1, 'first_name': 1, 'last_name': 1, 'email': 1}  # Select these fields
                    )
                    print(user, token_parts[1])
                    # Add use to global
                    g.user = user

            except ValueError:
                allowed = False

            if user and user['user_name']:
                allowed = True
        if not allowed:
            return jsonify(status='loginfail')

        return f(*args, **kwargs)

    return decorated_function
