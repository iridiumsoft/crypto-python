from flaskext.mysql import MySQL

import os
from dotenv import load_dotenv

load_dotenv('.env')


class Database:
    def __init__(self, app):
        mysql = MySQL()
        # MySQL configurations
        app.config['MYSQL_DATABASE_USER'] = os.getenv('MYSQL_DATABASE_USER')
        app.config['MYSQL_DATABASE_PASSWORD'] = os.getenv('MYSQL_DATABASE_PASSWORD')
        app.config['MYSQL_DATABASE_DB'] = os.getenv('MYSQL_DATABASE_DB')
        app.config['MYSQL_DATABASE_HOST'] = os.getenv('MYSQL_DATABASE_HOST')
        self.conn = mysql.connect()
        self.cursor = conn.cursor()
