import sqlite3
from ccxt import bitfinex2
import configparser
import json
from datetime import datetime
import time
import logging
from btfxwss import BtfxWss  # https://github.com/Crypto-toolbox/btfxwss
from threading import Thread

logger = logging.getLogger()
# logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
file_handler = logging.FileHandler('info.log')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)


class sqliteDB():
    def __init__(self):
        self.databaseFile = sqlite3.connect('database.db', timeout=30)
        self.databaseFile.text_factory = str
        self.QueryCurs = self.databaseFile.cursor()

    def create_table(self, table_name):
        table_name = table_name.replace("/", "")
        logger.info("Creation of %s", table_name)
        query = '''CREATE TABLE IF NOT EXISTS {} (id INTEGER PRIMARY KEY, mts INTEGER, open REAL, high REAL, low REAL,
                    close REAL, volume REAL)'''.format(table_name)
        self.QueryCurs.execute(query)
        logger.info("%s created successfully", table_name)

    def truncate_table(self, table_name):
        table_name = table_name.replace("/", "")
        logger.info("Deletion of %s", table_name)
        query = '''DELETE FROM {}'''.format(table_name)
        self.QueryCurs.execute(query)
        logger.info("%s emptied successfully", table_name)

    def getting_table_data(self, table_name):
        table_name = table_name.replace("/", "")
        logger.info("Getting data from %s", table_name)
        query = '''SELECT * FROM {}'''.format(table_name)
        self.QueryCurs.execute(query)
        data = self.QueryCurs.fetchall()

        logger.info("%s data selected successfully", table_name)
        if len(data) > 0:
            return data
        else:
            return None

    def add_candle(self, table_name, new_candle):
        table_name = table_name.replace("/", "")
        logger.debug("Adding candle to %s", table_name)
        query = '''INSERT INTO {} (mts, open, high, low, close, volume) VALUES (?,?,?,?,?,?)'''.format(table_name)
        self.QueryCurs.execute(query, (new_candle['mts'], new_candle['open'], new_candle['high'], new_candle['low'],
                                       new_candle['close'], new_candle['volume']))


class BitfinexData(sqliteDB):
    def __init__(self):
        super(BitfinexData, self).__init__()

        self.config_file = configparser.ConfigParser()
        self.config_file.read('config.ini')
        self.pairs = json.loads(self.config_file.get("Trading", "pairs"))
        self.timeframes = ['5m', '15m', '30m', '1h']
        self.tf_sminutes = {'5m': 5, '15m': 15, '30m': 30, '1h': 60, '3h': 180, '6h': 360}
        self.tf_seconds = {'5m': 30, '15m': 900, '30m': 1800, '1h': 3600, '3h': 10800, '6h': 21600}

        self.threadCollection = {}
        self.lastUpdate = {}
        self.spreads = {}
        self.price_precision = {}
        self.amount_precision = {}
        self.local_db = {}
        self.volume_data = {}
        self.last_volume_request = 0
        self.list_ready = []

        self.limit_orders = {}
        self.positions = {}

        self.target_profit = float(self.config_file.get("Trading", "target_profit")) / 100
        self.stop_loss = float(self.config_file.get("Trading", "stop_loss")) / 100
        self.critical_level = float(self.config_file.get("Trading", "critical_level")) / 100

        self.rest_client = bitfinex2({
            'apiKey': self.config_file.get("API", "key"),
            'secret': self.config_file.get("API", "secret"),
        })

        self.market_info = self.rest_client.fetch_markets()

        self.wss = BtfxWss(self.config_file.get("API", "key"), self.config_file.get("API", "secret"))
        self.start_websocket()

    def launch_all(self):

        self.thread_account = Thread(target=self.add_listener_account)
        self.thread_account.start()

        for pair in self.pairs:

            self.spreads[pair.replace("/", "")] = {'Bid': None, 'Ask': None}
            self.local_db[pair.replace("/", "")] = {}

            for el in self.market_info:
                if el['symbol'] == pair:
                    self.price_precision[pair.replace("/", "")] = el['precision']['price']
                    self.amount_precision[pair.replace("/", "")] = el['precision']['amount']
                    break

            self.threadCollection[pair] = Thread(target=self.add_listener, args=(pair.replace("/", ""),))
            self.threadCollection[pair].start()

            for tf in self.timeframes:

                db_object = sqliteDB()

                self.local_db[pair.replace("/", "")][tf] = []
                self.last_candle = None

                db_object.create_table(pair + "_" + tf)
                db_object.databaseFile.commit()
                db_data = db_object.getting_table_data(pair + "_" + tf)
                if db_data:
                    if int(time.time()) - 60 * self.tf_sminutes[tf] > db_data[-1][0]:

                        nb_missing = round((((int(time.time()) - db_data[-1][1]) / 60) / self.tf_sminutes[tf]) - 0.5)

                        if nb_missing > 450:
                            logger.warning("Too many missing data for %s %s (%s), requesting new initial data...", pair,
                                           tf, nb_missing)
                            db_object.truncate_table(pair + "_" + tf)
                            db_object.databaseFile.commit()
                            nb_missing = 450

                        if nb_missing > 0:
                            logger.warning("Missing %s candles for %s %s", nb_missing, pair, tf)
                            requested_data = self.rest_client.fetch_ohlcv(pair, timeframe=tf, limit=int(nb_missing))

                            if len(requested_data) == 0:
                                continue

                            for candle in requested_data[:-1]:

                                if self.last_candle:
                                    candles_gap = (int(candle[0] / 1000) - self.last_candle['mts']) / self.tf_seconds[
                                        tf]
                                    if candles_gap > 1:
                                        for i in range(1, int(candles_gap)):
                                            new_candle = {'mts': self.last_candle['mts'] + self.tf_seconds[tf] * i,
                                                          'open': self.last_candle['close'],
                                                          'high': self.last_candle['close'],
                                                          'low': self.last_candle['close'],
                                                          'close': self.last_candle['close'], 'volume': 0}
                                            db_object.add_candle(pair + "_" + tf, new_candle)

                                new_candle = {'mts': int(candle[0] / 1000), 'open': candle[1], 'high': candle[2],
                                              'low': candle[3],
                                              'close': candle[4], 'volume': candle[5]}
                                self.last_candle = new_candle
                                db_object.add_candle(pair + "_" + tf, new_candle)

                else:
                    logger.info("%s is empty, requesting initial data...", pair + "_" + tf)
                    requested_data = self.rest_client.fetch_ohlcv(pair, timeframe=tf, limit=450)

                    if len(requested_data) == 0:
                        continue

                    for candle in requested_data[:-1]:

                        if self.last_candle:
                            candles_gap = (int(candle[0] / 1000) - self.last_candle['mts']) / self.tf_seconds[tf]
                            if candles_gap > 1:
                                for i in range(1, int(candles_gap)):
                                    new_candle = {'mts': self.last_candle['mts'] + self.tf_seconds[tf] * i,
                                                  'open': self.last_candle['close'],
                                                  'high': self.last_candle['close'], 'low': self.last_candle['close'],
                                                  'close': self.last_candle['close'], 'volume': 0}
                                    db_object.add_candle(pair + "_" + tf, new_candle)

                        new_candle = {'mts': int(candle[0] / 1000), 'open': candle[1], 'high': candle[2],
                                      'low': candle[3],
                                      'close': candle[4], 'volume': candle[5]}
                        self.last_candle = new_candle
                        db_object.add_candle(pair + "_" + tf, new_candle)

                db_object.databaseFile.commit()

                db_data = db_object.getting_table_data(pair + "_" + tf)

                for candle in db_data:
                    self.local_db[pair.replace("/", "")][tf].append({'mts': candle[1], 'open': candle[2],
                                                                     'high': candle[3],
                                                                     'low': candle[4],
                                                                     'close': candle[5],
                                                                     'volume': candle[6]})

                self.local_db[pair.replace("/", "")][tf].append({'mts': int(requested_data[-1][0] / 1000),
                                                                 'open': requested_data[-1][1],
                                                                 'high': requested_data[-1][2],
                                                                 'low': requested_data[-1][3],
                                                                 'close': requested_data[-1][4],
                                                                 'volume': requested_data[-1][5]})

                self.list_ready.append(pair.replace("/", "") + "_" + tf)

                db_object.databaseFile.close()

                time.sleep(5)

    def start_websocket(self):

        """
        Establish the connection to the Bitfinex websocket
        """

        try:
            self.wss.start()
            while not self.wss.conn.connected.is_set():
                time.sleep(1)

            self.wss.subscribe_to_ticker('BTCEUR')  # To avoid being disconnected immediately
            self.wss.authenticate()
            logger.info("Authenticated")
            return True

        except Exception as e:
            print("Exception  " + str(e))
            return False

    def add_listener(self, asset):

        """
        Start listening to the given channel
        """

        self.wss.subscribe_to_ticker(asset)

        connectionEstablished = False

        while not connectionEstablished:
            try:
                ticker_q = self.wss.tickers(asset)
                connectionEstablished = True
                logger.info("Connection established for %s 1m streaming", asset)
            except Exception as e:
                pass

        self.lastUpdate[asset] = None

        while True:
            if not ticker_q.empty():
                received_price = ticker_q.get()
                self.parse_tickers(received_price, asset)

    def add_listener_account(self):

        connectionEstablished = False

        while not connectionEstablished:
            try:
                account_q = self.wss.account
                connectionEstablished = True
                logger.info("Connection established for account updates")
            except Exception as e:
                logger.warning("%s", e)
                time.sleep(1)

        while True:
            if not account_q.empty():
                received_info = account_q.get()
                self.parse_orders(received_info)

    def parse_orders(self, data):

        logger.info("%s", data)

        if data[0] == 'on':
            if data[1][0][8] == 'LIMIT':

                if data[1][0][7] > 0:
                    trade_trigger = "LONG"
                else:
                    trade_trigger = "SHORT"

                pair = data[1][0][3][1:]

                new_order = {"pair": pair, "side": trade_trigger, "entry_price": data[1][0][16],
                             "status": "open", "exit_price": None, "size": data[1][0][7], "entry_time": datetime.now(),
                             "exit_time": None, 'orderId': data[1][0][0]}
                self.limit_orders[data[1][0][0]] = new_order

        if data[0] == 'oc' or data[0] == 'ou':

            if data[1][0][13] == 'CANCELED':
                order = self.limit_orders[data[1][0][0]]
                logger.warning("Order %s %s cancelled", order['side'], order['pair'])

            elif data[1][0][8] == 'LIMIT':
                order = self.limit_orders[data[1][0][0]]

                if data[1][0][0] not in self.positions:

                    if order['side'] == 'LONG':
                        new_position = {"pair": order['pair'],
                                        "side": order['side'],
                                        "entry_price": order['entry_price'],
                                        "status": "open",
                                        "exit_price": None,
                                        "size": data[1][0][7],
                                        "entry_time": datetime.now(),
                                        "exit_time": None,
                                        'tp': order['entry_price'] * (1 + self.target_profit),
                                        'sl': order['entry_price'] * (1 - self.stop_loss),
                                        'critical_point': order['entry_price'] * (1 - self.critical_level)
                                        }

                    else:
                        new_position = {"pair": order['pair'],
                                        "side": order['side'],
                                        "entry_price": order['entry_price'],
                                        "status": "open",
                                        "exit_price": None,
                                        "size": abs(data[1][0][7]),
                                        "entry_time": datetime.now(),
                                        "exit_time": None,
                                        'tp': order['entry_price'] * (1 - self.target_profit),
                                        'sl': order['entry_price'] * (1 + self.stop_loss),
                                        'critical_point': order['entry_price'] * (1 + self.critical_level)
                                        }

                    # Insert query to the database and add a new position
                    # When a new order was placed
                    order_id = data[1][0][0]
                    self.positions[order_id] = new_position

                else:
                    order_id = data[1][0][0]
                    self.positions[order_id]['size'] = abs(data[1][0][7])

                if data[0] == 'oc':
                    order['status'] = 'filled'

    def parse_tickers(self, data, pair):

        self.spreads[pair]['Bid'] = data[0][0][0]
        self.spreads[pair]['Ask'] = data[0][0][2]

        temp_mid = (self.spreads[pair]['Bid'] + self.spreads[pair]['Bid']) / 2

        for tf in self.timeframes:

            if not pair + "_" + tf in self.list_ready:
                continue

            nb_missing = round((((data[1] - self.local_db[pair][tf][-1]['mts']) / 60) / self.tf_sminutes[tf]) - 0.5)
            # print(pair, tf, data, self.local_db[pair][tf][-1]['mts'], nb_missing)
            if nb_missing == 0:
                self.local_db[pair][tf][-1]['close'] = temp_mid
                if temp_mid > self.local_db[pair][tf][-1]['high']:
                    self.local_db[pair][tf][-1]['high'] = temp_mid
                if temp_mid < self.local_db[pair][tf][-1]['low']:
                    self.local_db[pair][tf][-1]['low'] = temp_mid
            elif nb_missing > 1:
                logger.info("Adding %s candles to %s %s", nb_missing - 1, pair, tf)
                db_object = sqliteDB()

                for i in range(nb_missing - 1):
                    self.local_db[pair][tf].append(
                        {'mts': self.local_db[pair][tf][-1]['mts'] + self.tf_sminutes[tf] * 60,
                         'open': self.local_db[pair][tf][-1]['close'],
                         'high': self.local_db[pair][tf][-1]['close'],
                         'low': self.local_db[pair][tf][-1]['close'],
                         'close': self.local_db[pair][tf][-1]['close']})
                    new_candle = {'mts': self.local_db[pair][tf][-2]['mts'],
                                  'open': self.local_db[pair][tf][-2]['open'],
                                  'high': self.local_db[pair][tf][-2]['high'],
                                  'low': self.local_db[pair][tf][-2]['low'],
                                  'close': self.local_db[pair][tf][-2]['close'],
                                  'volume': 0}
                    db_object.add_candle(pair + "_" + tf, new_candle)

                self.local_db[pair][tf].append({'mts': self.local_db[pair][tf][-1]['mts'] + self.tf_sminutes[tf] * 60,
                                                'open': temp_mid,
                                                'high': temp_mid,
                                                'low': temp_mid,
                                                'close': temp_mid})

                new_candle = {'mts': self.local_db[pair][tf][-2]['mts'], 'open': self.local_db[pair][tf][-2]['open'],
                              'high': self.local_db[pair][tf][-2]['high'],
                              'low': self.local_db[pair][tf][-2]['low'],
                              'close': self.local_db[pair][tf][-2]['close'],
                              'volume': 0}
                db_object.add_candle(pair + "_" + tf, new_candle)

                while True:
                    try:
                        db_object.databaseFile.commit()
                        break
                    except sqlite3.OperationalError:
                        continue
                db_object.databaseFile.close()

            elif nb_missing == 1:

                db_object = sqliteDB()

                logger.info("Adding new candle to %s %s", pair, tf)

                new_candle = {'mts': self.local_db[pair][tf][-1]['mts'], 'open': self.local_db[pair][tf][-1]['open'],
                              'high': self.local_db[pair][tf][-1]['high'],
                              'low': self.local_db[pair][tf][-1]['low'],
                              'close': self.local_db[pair][tf][-1]['close'],
                              'volume': 0}
                try:
                    db_object.add_candle(pair + "_" + tf, new_candle)
                    self.local_db[pair][tf].append(
                        {'mts': self.local_db[pair][tf][-1]['mts'] + self.tf_sminutes[tf] * 60,
                         'open': temp_mid,
                         'high': temp_mid,
                         'low': temp_mid,
                         'close': temp_mid})
                except Exception as e:
                    logger.error("Error while adding candle: %s", e)

                while True:
                    try:
                        db_object.databaseFile.commit()
                        break
                    except sqlite3.OperationalError:
                        continue
                db_object.databaseFile.close()
