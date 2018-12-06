from flask import Blueprint, request, g, jsonify

# import Vincent Code
from vincent.trading import BitfinexData, TradingBot

api = Blueprint('api', __name__, url_prefix='/')

#
# # Run Vincent Bot
data_collector = BitfinexData()
trading_bot = TradingBot(data_collector)


#
#
def objToArray(ob):
    dictlist = []
    for key, value in ob:
        # temp = [key, value]
        dictlist.append(value)
    print(dictlist)
    return dictlist


# #
@api.route('/limit-orders', methods=['GET'])
def get_orders():
    return jsonify(data_collector.limit_orders.values())
#
#
# @api.route('/positions', methods=['GET'])
# def get_orders():
#     return jsonify(objToArray(data_collector.positions))
