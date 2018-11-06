from data_management import BitfinexData
from technical_analysis import *
from threading import Thread
import pandas as pd
import logging
import time
import sys
import configparser
from datetime import datetime, timedelta


logger = logging.getLogger()
logger.setLevel(logging.INFO)


class TradingBot():
    def __init__(self, dataObject):

        self.macd_res = {}
        self.dema_res_1 = {}
        self.dema_res_2 = {}
        self.adx_res = {}
        self.sar_res = {}
        self.volume_df = {}

        self.tf_weights = {'5m': 15 , '15m': 35, '30m': 25, '1h': 25}
        self.sl_timeframe = '30m'

        if sum(self.tf_weights.values()) != 100:
            logger.warning("Weights must be equal to 100 (%s currently)", sum(self.tf_weights.values()))
            sys.exit()

        self.dataObject = dataObject

        self.config_file = configparser.ConfigParser()
        self.config_file.read('config.ini')
        self.trading_type = self.config_file.get("Trading", "trading_type")
        self.trade_size = float(self.config_file.get("Trading", "trade_size"))
        self.target_profit = float(self.config_file.get("Trading", "target_profit")) / 100
        self.trailing_sl = float(self.config_file.get("Trading", "trailing_sl")) / 100
        self.stop_loss = float(self.config_file.get("Trading", "stop_loss")) / 100
        self.limit_level = float(self.config_file.get("Trading", "limit_level")) / 100

        self.cancel_after = int(self.config_file.get("Trading", "cancel_after"))
        self.critical_level = float(self.config_file.get("Trading", "critical_level")) / 100
        self.critical_exit = float(self.config_file.get("Trading", "critical_exit")) / 100

        self.file_name = "trading_log_" + datetime.now().strftime('%d%m%Y_%H%M%S')
        self.last_trade_log = time.time()

        t = Thread(target=self.dataObject.launch_all)
        t.start()

        t_entry = Thread(target=self.entry_check)
        t_entry.start()

    def update_daily_volume(self):
        try:
            new_data = self.dataObject.rest_client.fetch_tickers()
        except Exception as e:
            logger.error("Error while getting tickers info: %s", e)
            return

        for elem in new_data:
            self.dataObject.volume_data[elem.replace("/", "")] = new_data[elem]['baseVolume'] * new_data[elem]['last']
        logger.info("Update daily volume data")

    def entry_check(self):

        while True:

            logger.debug("Checking entries...")

            if time.time() - 600 > self.last_trade_log:
                report_string = ""
                for pos_temp in self.dataObject.positions:
                    pos = self.dataObject.positions[pos_temp]
                    if pos['status'] == 'closed':
                        if pos['side'] == "LONG":
                            pct_pnl = round((pos['exit_price'] / pos['entry_price'] - 1) * 100, 2)
                        else:
                            pct_pnl = round((pos['entry_price'] / pos['exit_price'] - 1) * 100, 2)

                        report_string += pos['side'] + " " + pos['pair'] + " : Entry " + str(pos['size']) + "@" + str(pos['entry_price']) \
                                      + " on " + pos['entry_time'].strftime('%d-%m-%Y %H:%M:%S') + " | " \
                                      + " Closed @" + str(pos['exit_price']) + " on " + pos['exit_time'].strftime('%d-%m-%Y %H:%M:%S') \
                                      + " ||| " + str(pct_pnl) + "%\n"

                f = open(self.file_name + ".txt", "w")
                f.write(report_string)

                self.last_trade_log = time.time()

            self.check_limit_orders()

            for pos_temp in self.dataObject.positions:
                pos = self.dataObject.positions[pos_temp]
                if pos['status'] == "open":
                    if pos['side'] == "LONG":
                        current_pnl_euro = pos['size'] * (self.dataObject.spreads[pos['pair']]['Bid'] - pos['entry_price'])
                    else:
                        current_pnl_euro = pos['size'] * (pos['entry_price'] - self.dataObject.spreads[pos['pair']]['Ask'])
                    logger.info("Current position: %s %s %s@%s opened at %s | PNL: %s €", pos['side'], pos['pair'], pos['size'],
                                pos['entry_price'], pos['entry_time'].strftime('%d-%m-%Y %H:%M:%S'), round(current_pnl_euro, 2))

            if time.time() - 3600 > self.dataObject.last_volume_request:
                self.update_daily_volume()
                self.dataObject.last_volume_request = time.time()

            for pair in self.dataObject.pairs:

                already_open = False
                for pos_temp in self.dataObject.positions:
                    pos = self.dataObject.positions[pos_temp]
                    if pos['pair'] == pair.replace("/", "") and pos['status'] == "open":
                        already_open = True
                        try:
                            df = pd.DataFrame(self.dataObject.local_db[pair.replace("/", "")][self.sl_timeframe])
                        except Exception as e:
                            logger.error("Error while creating dataframe for %s: %s", pair.replace("/", ""), e)
                            break
                        self.sar_res[pair.replace("/", "") + "_" + self.sl_timeframe] = sar(df) # Since we need it for stop loss
                        break

                for ord_temp in self.dataObject.limit_orders:
                    ord = self.dataObject.limit_orders[ord_temp]
                    if ord['pair'] == pair.replace("/", "") and ord['status'] == "open":
                        already_open = True
                        break

                self.check_exit(pair.replace("/", ""))

                if already_open:
                    continue

                pair = pair.replace("/", "")

                long_points_macd = 0
                short_points_macd = 0
                total_points_macd = 0

                long_points_dema = 0
                short_points_dema = 0
                total_points_dema = 0

                long_points_adx = 0
                short_points_adx = 0
                total_points_adx = 0

                for tf in self.dataObject.timeframes:
                    if not pair + "_" + tf in self.dataObject.list_ready:
                        continue
                    try:
                        df = pd.DataFrame(self.dataObject.local_db[pair][tf])
                    except ValueError as e:
                        logger.error("%s %s: %s", pair, tf, e)
                        continue

                    self.macd_res[pair + "_" + tf] = macd(df['close'].tolist(), 12, 26, 9)
                    self.dema_res_1[pair + "_" + tf] = dema(df['close'].tolist(), 9)
                    self.dema_res_2[pair + "_" + tf] = dema(df['close'].tolist(), 26)
                    self.adx_res[pair + "_" + tf] = adx(df['high'].tolist(), df['low'].tolist(), 14)
                    self.sar_res[pair + "_" + tf] = sar(df)
                    self.volume_df[pair + "_" + tf] = df['volume']

                    """ MACD """

                    current_avg_range = avg_range(df['high'].tolist(), df['low'].tolist(), 14)
                    if self.macd_res[pair + "_" + tf][1][-1]:
                        current_signal_macd = self.macd_res[pair + "_" + tf][0][-1] - self.macd_res[pair + "_" + tf][1][-1]
                    else:
                        current_signal_macd = 0

                    if current_avg_range != 0:
                        if current_signal_macd  > 0 and (current_signal_macd / current_avg_range) * 100 > 0.5:
                            long_points_macd += (current_signal_macd / current_avg_range) * self.tf_weights[tf]
                            total_points_macd += (current_signal_macd / current_avg_range) * self.tf_weights[tf]
                        elif current_signal_macd < 0 and abs(current_signal_macd / current_avg_range) * 100 > 0.5:
                            short_points_macd += (abs(current_signal_macd) / current_avg_range) * self.tf_weights[tf]
                            total_points_macd += (abs(current_signal_macd) / current_avg_range) * self.tf_weights[tf]

                    """ DEMA """

                    if self.dema_res_1[pair + "_" + tf][-1] > self.dema_res_2[pair + "_" + tf][-1] \
                        and any(self.dema_res_1[pair + "_" + tf][-x] < self.dema_res_2[pair + "_" + tf][-x] for x in range(1, 4)):
                        long_points_dema += self.tf_weights[tf]
                        total_points_dema += self.tf_weights[tf]
                    elif self.dema_res_1[pair + "_" + tf][-1] < self.dema_res_2[pair + "_" + tf][-1] \
                        and any(self.dema_res_1[pair + "_" + tf][-x] > self.dema_res_2[pair + "_" + tf][-x] for x in range(1, 4)):
                        short_points_dema += self.tf_weights[tf]
                        total_points_dema += self.tf_weights[tf]


                    """ ADX """

                    if self.adx_res[pair + "_" + tf][0][-1] > 20:
                        if self.adx_res[pair + "_" + tf][2][-1] > self.adx_res[pair + "_" + tf][1][-1]:
                            long_points_adx += self.tf_weights[tf]
                            total_points_adx += self.tf_weights[tf]
                        elif self.adx_res[pair + "_" + tf][2][-1] < self.adx_res[pair + "_" + tf][1][-1]:
                            short_points_adx += self.tf_weights[tf]
                            total_points_adx += self.tf_weights[tf]

                if total_points_macd > 0:
                    long_macd = (long_points_macd / total_points_macd) * 100
                    short_macd = (short_points_macd / total_points_macd) * 100
                else:
                    long_macd = 0
                    short_macd = 0

                if total_points_dema > 0:
                    long_dema = (long_points_dema / total_points_dema) * 100
                    short_dema = (short_points_dema / total_points_dema) * 100
                else:
                    long_dema = 0
                    short_dema = 0

                if total_points_adx > 0:
                    long_adx = (long_points_adx / total_points_adx) * 100
                    short_adx = (short_points_adx / total_points_adx) * 100
                else:
                    long_adx = 0
                    short_adx = 0

                trade_trigger = None

                if pair + '_1h' in self.volume_df:
                    logger.info("%s LONG: MACD %s%% DEMA %s%% ADX %s%% SAR side %s", pair, '{:.1f}'.format(long_macd),
                                '{:.1f}'.format(long_dema), '{:.1f}'.format(long_adx),
                                round(self.sar_res[pair + '_' + self.sl_timeframe]['SAR'][-1], self.dataObject.amount_precision[pair]))
                    logger.info("%s SHORT: MACD %s%% DEMA %s%% ADX %s%% SAR side %s", pair, '{:.1f}'.format(short_macd),
                                '{:.1f}'.format(short_dema), '{:.1f}'.format(short_adx),
                                round(self.sar_res[pair + '_' + self.sl_timeframe]['SAR'][-1], self.dataObject.amount_precision[pair]))
                    if self.dataObject.volume_data[pair.replace("/", "")] > 50000:
                        if long_macd > 50 and long_dema > 50 and long_adx > 50 and self.sar_res[pair + '_' + self.sl_timeframe]['direction'][-1] == 1:
                            trade_trigger = "LONG"
                        elif short_macd > 50 and short_dema > 50 and short_adx > 50 and self.sar_res[pair + '_' + self.sl_timeframe]['direction'][-1] == -1:
                            trade_trigger = "SHORT"

                if pair not in self.dataObject.local_db:
                    continue
                if '1h' not in self.dataObject.local_db[pair]:
                    continue

                if len(self.dataObject.local_db[pair]['15m']) < 2:
                    continue

                recent_var = (self.dataObject.local_db[pair]['15m'][-1]['close'] / self.dataObject.local_db[pair]['15m'][-2]['low'] - 1) * 100
                if abs(recent_var) >= 4:
                    continue

                if trade_trigger:

                    orderId = int(time.time() * 1000)

                    if trade_trigger == "LONG":
                        bitfinex_pair = pair.replace("EUR", "") + "/EUR"
                        trade_size = round(self.trade_size / self.dataObject.spreads[pair]['Ask'], self.dataObject.amount_precision[pair])
                        logger.warning("Limit buy order %s %s at %s, current ask %s", trade_size, pair.replace("EUR", ""),
                                       self.dataObject.spreads[pair]['Ask'] * (1 - self.limit_level),
                                       self.dataObject.spreads[pair]['Ask'])
                        limit_price = self.dataObject.spreads[pair]['Ask'] * (1 - self.limit_level)

                        if self.trading_type == "DEMO":
                            new_order = {"pair": pair, "side": trade_trigger, "entry_price": self.dataObject.spreads[pair]['Ask'],
                                            "status": "open", "exit_price": None, "size": trade_size, "entry_time": datetime.now(),
                                            "exit_time": None, 'orderId': str(orderId)}
                            self.dataObject.limit_orders[orderId] = new_order
                        else:
                            try:
                                self.dataObject.wss.new_order(cid=orderId, type='LIMIT', symbol='t' + pair,
                                                              price=str(limit_price), amount=str(trade_size))
                            except Exception as e:
                                logger.warning("Failed to enter long position for %s: %s", pair, e)

                    elif trade_trigger == "SHORT":
                        bitfinex_pair = pair.replace("EUR", "") + "/EUR"
                        trade_size = round(self.trade_size / self.dataObject.spreads[pair]['Bid'], self.dataObject.amount_precision[pair])
                        logger.warning("Limit sell order %s %s at %s, current bid %s", trade_size, pair.replace("EUR", ""),
                                       self.dataObject.spreads[pair]['Bid'] * (1 + self.limit_level),
                                       self.dataObject.spreads[pair]['Bid'])
                        limit_price = self.dataObject.spreads[pair]['Bid'] * (1 + self.limit_level)

                        if self.trading_type == "DEMO":
                            new_order = {"pair": pair, "side": trade_trigger, "entry_price": self.dataObject.spreads[pair]['Bid'],
                                            "status": "open", "exit_price": None, "size": trade_size, "entry_time": datetime.now(),
                                            "exit_time": None, 'orderId': str(orderId)}
                            self.dataObject.limit_orders[orderId] = new_order
                        else:
                            try:
                                self.dataObject.wss.new_order(cid=orderId, type='LIMIT', symbol='t' + pair,
                                                               price=str(limit_price), amount=str(-trade_size))
                            except Exception as e:
                                logger.warning("Failed to enter short position for %s: %s", pair, e)

            time.sleep(5)
            print("\n")

    def check_limit_orders(self):

        spreads = self.dataObject.spreads

        for order_key in self.dataObject.limit_orders:

            order = self.dataObject.limit_orders[order_key]

            if order['status'] == 'open':

                logger.info('Current limit order: %s', order)

                if datetime.now() - timedelta(minutes=self.cancel_after) >= order['entry_time'] and order['status'] == 'open':
                    logger.info("Cancelling limit order for %s %s (still no entry after %s minutes", order['side'],
                                order['pair'], self.cancel_after)

                    if self.trading_type == 'LIVE':
                        try:
                            self.dataObject.wss.cancel_order(multi=False, id=order['orderId'])
                            order['status'] = 'cancelled'
                        except Exception as e:
                            logger.error("Error while cancelling order: %s", e)
                    else:
                        order['status'] = 'cancelled'

                if self.trading_type != 'DEMO':
                    continue

                if order['side'] == 'LONG' and spreads[order['pair']]['Ask'] <= order['entry_price'] * (1 - self.limit_level):
                    new_position = {"pair": order['pair'],
                                    "side": order['side'],
                                    "entry_price": spreads[order['pair']]['Ask'],
                                    "status": "open",
                                    "exit_price": None,
                                    "size": order['size'],
                                    "entry_time": datetime.now(),
                                    "exit_time": None,
                                    'tp': spreads[order['pair']]['Ask'] * (1 + self.target_profit),
                                    'sl': spreads[order['pair']]['Ask'] * (1 - self.stop_loss),
                                    'critical_point': spreads[order['pair']]['Ask'] * (1 - self.critical_level)
                                    }
                    self.dataObject.positions[order['orderId']] = new_position
                    order['status'] = 'filled'

                elif order['side'] == 'SHORT' and spreads[order['pair']]['Bid'] >= order['entry_price'] * (1 + self.limit_level):
                    new_position = {"pair": order['pair'],
                                    "side": order['side'],
                                    "entry_price": self.dataObject.spreads[order['pair']]['Bid'],
                                    "status": "open",
                                    "exit_price": None,
                                    "size": order['size'],
                                    "entry_time": datetime.now(),
                                    "exit_time": None,
                                    'tp': spreads[order['pair']]['Bid'] * (1 - self.target_profit),
                                    'sl': spreads[order['pair']]['Bid'] * (1 + self.stop_loss),
                                    'critical_point': spreads[order['pair']]['Bid'] * (1 + self.critical_level)
                                    }
                    self.dataObject.positions[order['orderId']] = new_position
                    order['status'] = 'filled'

    def check_exit(self, pair):

        spreads = self.dataObject.spreads

        for pos_temp in self.dataObject.positions:
            pos = self.dataObject.positions[pos_temp]
            if pos['pair'] == pair and pos['status'] == "open":

                bitfinex_pair = pair.replace("EUR", "") + "/EUR"

                if pos['side'] == "LONG":
                    if spreads[pair]['Bid'] <= pos['critical_point']:
                        pos['tp'] = pos['entry_price'] * (1 - self.critical_exit)

                    if spreads[pair]['Bid'] >= pos['tp']:
                        pos['sl'] = pos['tp'] * (1 - self.trailing_sl)
                        pos['tp'] = pos['tp'] * (1 + self.trailing_sl)
                        logger.warning("Updating TP (%s) and SL (%s) for %s", pos['tp'], pos['sl'], pair)
                    elif spreads[pair]['Bid'] <= pos['sl']:
                        if self.trading_type == "DEMO":
                            pos['status'] = 'closed'
                            pos['exit_price'] = spreads[pair]['Bid']
                            pos['exit_time'] = datetime.now()
                        else:
                            orderId = int(time.time() * 1000)
                            try:
                                self.dataObject.wss.new_order(cid=orderId, type='MARKET', symbol='t' + pair,
                                                           amount=str(-pos['size']))
                            except Exception as e:
                                logger.error("Error while closing long position: %s", e)
                                continue
                            pos['exit_price'] = spreads[pair]['Ask']
                            pos['exit_time'] = datetime.now()
                            pos['status'] = 'closed'

                if pos['side'] == "SHORT":
                    if spreads[pair]['Ask'] >= pos['critical_point']:
                        pos['tp'] = pos['entry_price'] * (1 + self.critical_exit)
                        
                    if spreads[pair]['Ask'] <= pos['tp']:
                        pos['sl'] = pos['tp'] * (1 + self.trailing_sl)
                        pos['tp'] = pos['tp'] * (1 - self.trailing_sl)
                        logger.warning("Updating TP (%s) and SL (%s) for %s", pos['tp'], pos['sl'], pair)
                    elif spreads[pair]['Ask'] >= pos['sl']:
                        if self.trading_type == "DEMO":
                            pos['status'] = 'closed'
                            pos['exit_price'] = spreads[pair]['Ask']
                            pos['exit_time'] = datetime.now()
                        else:
                            orderId = int(time.time() * 1000)
                            try:
                                self.dataObject.wss.new_order(cid=orderId, type='MARKET', symbol='t' + pair,
                                                          amount=str(pos['size']))
                            except Exception as e:
                                logger.error("Error while closing short position: %s", e)
                                continue
                            pos['exit_price'] = spreads[pair]['Ask']
                            pos['exit_time'] = datetime.now()
                            pos['status'] = 'closed'


if __name__ == '__main__':
    data_collector = BitfinexData()
    trading_bot = TradingBot(data_collector)

    while True:
        pass
