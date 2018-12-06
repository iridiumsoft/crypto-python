import pandas as pd


def avg_range(data_high, data_low, period):
    sum_ranges = 0
    for i in range(len(data_high)):
        sum_ranges += data_high[i] - data_low[i]

    return sum_ranges / period


def macd(data, short_tf, long_tf, signal_tf):
    multiplier_short = 2 / (short_tf + 1)
    multiplier_long = 2 / (long_tf + 1)
    multiplier_signal = 2 / (signal_tf + 1)

    """ SHORT EMA """

    ema_short = []

    for i in range(len(data)):
        if i < long_tf:
            ema_short.append(0)
            continue
        elif i == long_tf:
            ema_short.append(sum(data[i - short_tf:i]) / short_tf)
            continue

        new_ema = (data[i] - ema_short[-1]) * multiplier_short + ema_short[-1]
        ema_short.append(new_ema)

    """ LONG EMA """

    ema_long = []

    for i in range(len(data)):
        if i < long_tf:
            ema_long.append(0)
            continue
        elif i == long_tf:
            ema_long.append(sum(data[:i]) / long_tf)
            continue

        new_ema = (data[i] - ema_long[-1]) * multiplier_long + ema_long[-1]
        ema_long.append(new_ema)

    macd_line = [i - j for i, j in zip(ema_short, ema_long)]

    """ SIGNAL LINE """

    ema_signal = []

    for i in range(len(macd_line)):
        if i < long_tf:
            ema_signal.append(None)
            continue
        elif i == long_tf:
            ema_signal.append(sum(macd_line[:i]) / signal_tf)
            continue

        new_ema = (macd_line[i] - ema_signal[-1]) * multiplier_signal + ema_signal[-1]
        ema_signal.append(new_ema)

    return macd_line, ema_signal


def dema(data, tf):
    multiplier_short = 2 / (tf + 1)

    """ EMA """

    ema = []

    for i in range(len(data)):
        if i < tf:
            ema.append(0)
            continue
        elif i == tf:
            ema.append(sum(data[i - tf:i]) / tf)
            continue

        new_ema = (data[i] - ema[-1]) * multiplier_short + ema[-1]
        ema.append(new_ema)

    """ EMA_2 """

    ema_2 = []

    for i in range(len(ema)):
        if i < tf:
            ema_2.append(0)
            continue
        elif i == tf:
            ema_2.append(sum(ema[i - tf:i]) / tf)
            continue

        new_ema_2 = (ema[i] - ema_2[-1]) * multiplier_short + ema_2[-1]
        ema_2.append(new_ema_2)

    """ DEMA """

    dema = []

    for i in range(len(ema)):
        if i < tf:
            dema.append(0)
            continue

        new_dema = 2 * ema[i] - ema_2[i]
        dema.append(new_dema)

    return dema


def adx(data_high, data_low, tf):
    plus_di = [0]
    minus_di = [0]
    adx_curve = [0]
    plus_di_tf = [0]
    minus_di_tf = [0]
    dx_index = [0]
    plus_di_smooth = [0]
    minus_di_smooth = [0]

    for i in range(1, len(data_high)):

        var_high = data_high[i] - data_high[i - 1]
        var_low = data_low[i - 1] - data_low[i]

        if var_high <= 0:
            high_to_add = 0
        elif var_high > var_low:
            high_to_add = var_high
            low_to_add = 0

        if var_low <= 0:
            low_to_add = 0
        elif var_high < var_low:
            high_to_add = 0
            low_to_add = var_low

        if var_low == var_high:
            high_to_add = 0
            low_to_add = 0

        plus_di.append(high_to_add)
        minus_di.append(low_to_add)

    atr_curve = atr(data_high, data_low, tf)
    atr_curve_smooth = [0]

    for i in range(len(data_high)):
        if i < tf:
            plus_di_smooth.append(0)
            minus_di_smooth.append(0)
            continue
        elif i == tf:
            plus_di_smooth.append(sum(plus_di[i - tf:i]))
            minus_di_smooth.append(sum(minus_di[i - tf:i]))
            continue

        plus_di_smooth.append(plus_di_smooth[-1] - (plus_di_smooth[-1] / tf) + plus_di[i])
        minus_di_smooth.append(minus_di_smooth[-1] - (minus_di_smooth[-1] / tf) + minus_di[i])

    for i in range(len(data_high)):
        if i < tf:
            atr_curve_smooth.append(0)
            continue
        elif i == tf:
            atr_curve_smooth.append(sum(atr_curve[i - tf:i]))
            continue

        atr_curve_smooth.append(atr_curve_smooth[-1] - (atr_curve_smooth[-1] / tf) + atr_curve[i])

    for i in range(len(data_high)):
        if i < tf * 2:
            plus_di_tf.append(0)
            minus_di_tf.append(0)
            dx_index.append(0)
            continue

        if atr_curve_smooth[i] == 0:
            plus_di_tf.append(plus_di_tf[-1])
            minus_di_tf.append(minus_di_smooth[-1])
        else:
            plus_di_tf.append((plus_di_smooth[i] / atr_curve_smooth[i]) * 100)
            minus_di_tf.append((minus_di_smooth[i] / atr_curve_smooth[i]) * 100)

        if plus_di_tf[i] == 0 and minus_di_tf[i] == 0:
            dx_index.append(0)
            continue

        dx_index.append(abs((plus_di_tf[i] - minus_di_tf[i]) / (plus_di_tf[i] + minus_di_tf[i])) * 100)

    for i in range(tf, len(data_high)):
        if i < tf * 2:
            adx_curve.append(0)
            continue

        if i == tf * 2:
            adx_curve.append(sum(dx_index[i - tf:i]) / tf)
            continue

        adx_curve.append((adx_curve[-1] * (tf - 1) + dx_index[i]) / tf)

    return adx_curve, minus_di_tf, plus_di_tf


def atr(data_high, data_low, tf):
    atr_curve = []

    for i in range(len(data_high)):
        if i < tf:
            atr_curve.append(0)
            continue
        elif i == tf:
            prior_atr = 0
            temp_high_data = data_high[i - 14:i]
            temp_low_data = data_low[i - 14:i]
            for x in range(len(temp_high_data)):
                prior_atr += temp_high_data[x] - temp_low_data[x]
            prior_atr = prior_atr / tf
            atr_curve.append((prior_atr * (tf - 1) + (data_high[i] - data_low[i])) / tf)
            continue

        atr_curve.append((atr_curve[i - 1] * (tf - 1) + (data_high[i] - data_low[i])) / tf)

    return atr_curve


def sar(data):
    data_high = data['high'].tolist()
    data_low = data['low'].tolist()
    mts_data = data['mts'].tolist()

    pd.set_option('display.width', 1000)

    sar_curve = [None, None, None, None]
    ep = [None, None, None, None]
    ep_sar = [None, None, None, None]
    af = [None, None, None, None]
    af_diff = [None, None, None, None]
    direction = [None, None, None, 1]

    sar_curve.append(min(data_low[:5]))
    ep.append(max(data_high[:5]))
    ep_sar.append(ep[-1] - sar_curve[-1])

    if direction[-1] == 1:
        if data_low[4] > sar_curve[-1]:
            direction.append(1)
        else:
            direction.append(-1)

    elif direction[-1] == -1:
        if data_high[4] < sar_curve[-1]:
            direction.append(-1)
        else:
            direction.append(1)
    # Ok
    # if direction[-1] == direction[-2]:
    #     if direction[-1] == 1:
    #         if ep[-1] > ep[-2]:
    #             if af[-1] == 0.2:
    #                 af.append(af[-1])
    #             else:
    #                 af.append(af[-1] + 0.02)
    #         else:
    #             af.append(af[-1])
    #     else:
    #         if ep[-1] < ep[-2]:
    #             if af[-1] == 0.2:
    #                 af.append(af[-1])
    #             else:
    #                 af.append(af[-1] + 0.02)
    #         else:
    #             af.append(af[-1])
    # else:
    #     af.append(0.02)
    af.append(0.02)

    af_diff.append(ep_sar[-1] * af[-1])

    for i in range(5, len(data_high)):

        """ Compute SAR """

        if direction[-1] == direction[-2]:
            if direction[-1] == 1:
                if sar_curve[-1] + af_diff[-1] < min(data_low[i - 1], data_low[i - 2]):
                    sar_curve.append(sar_curve[-1] + af_diff[-1])
                else:
                    sar_curve.append(min(data_low[i - 1], data_low[i - 2]))
            else:
                if sar_curve[-1] + af_diff[-1] > max(data_high[i - 1], data_high[i - 2]):
                    sar_curve.append(sar_curve[-1] + af_diff[-1])
                else:
                    sar_curve.append(max(data_high[i - 1], data_high[i - 2]))
        else:
            sar_curve.append(ep[-1])

        # if direction[-1] == 1 and sar_curve[-1] + af_diff[-1] > data_low[i - 1]:
        #     sar_curve.append(ep[-1])
        # elif direction[-1] == -1 and sar_curve[-1] + af_diff[-1] < data_high[i - 1]:
        #     sar_curve.append(ep[-1])
        # else:
        #     sar_curve.append(sar_curve[-1] + af_diff[-1])

        """ Direction """

        if direction[-1] == 1:
            if data_low[i] > sar_curve[-1]:
                direction.append(1)
            else:
                direction.append(-1)
        elif direction[-1] == -1:
            if data_high[i] < sar_curve[-1]:
                direction.append(-1)
            else:
                direction.append(1)

        # if sar_curve[-1] < data_high[i]:
        #     direction.append(1)
        # elif sar_curve[-1] > data_low[i]:
        #     direction.append(-1)
        # else:
        #     direction.append(0)

        """ EP """

        if direction[-2] == 1:
            if data_high[i] > ep[-1]:
                ep.append(data_high[i])
            else:
                ep.append(ep[-1])
        else:
            if data_low[i] < ep[-1]:
                ep.append(data_low[i])
            else:
                ep.append(ep[-1])

        # if direction[-1] == 1:
        #     if data_high[i] > ep[i - 1]:
        #         ep.append(data_high[i])
        #     else:
        #         ep.append(ep[-1])
        # else:
        #     if data_low[i] < ep[i - 1]:
        #         ep.append(data_low[i])
        #     else:
        #         ep.append(ep[-1])

        """ EP +/- SAR """

        ep_sar.append(ep[-1] - sar_curve[-1])

        """ AF """

        if direction[-1] == direction[-2]:
            if direction[-1] == 1:
                if ep[-1] > ep[-2]:
                    if af[-1] == 0.2:
                        af.append(af[-1])
                    else:
                        af.append(af[-1] + 0.02)
                else:
                    af.append(af[-1])
            else:
                if ep[-1] < ep[-2]:
                    if af[-1] == 0.2:
                        af.append(af[-1])
                    else:
                        af.append(af[-1] + 0.02)
                else:
                    af.append(af[-1])
        else:
            af.append(0.02)

        """ AF difference """

        af_diff.append(ep_sar[-1] * af[-1])

    df_temp = pd.DataFrame({'mts': pd.Series(mts_data),
                            'SAR': pd.Series(sar_curve),
                            'EP': pd.Series(ep),
                            'AF': pd.Series(af),
                            'direction': pd.Series(direction)
                            })
    df_temp['mts'] = pd.to_datetime(df_temp['mts'], unit='s')
    df_temp = df_temp.set_index(['mts'])

    return df_temp


def sar2(data):
    data_high = data['high'].tolist()
    data_low = data['low'].tolist()
    mts_data = data['mts'].tolist()

    pd.set_option('display.width', 1000)

    sar_curve = [None, None, None, None]
    ep = [None, None, None, None]
    af = [None, None, None, None]
    direction = [None, None, None, None]

    direction.append(1)
    ep.append(max(data_high[:5]))
    sar_curve.append(min(data_low[:5]))
    af.append(0.02)
    EPnew = 0
    AFnew = 0.02

    for i in range(5, len(data_high)):

        if direction[-1] == 0:
            direction.append(1)
        else:
            if direction[-1] == 1:
                EPnew = max(data_high[i], ep[-1])
            else:
                EPnew = min(data_low[i], ep[-1])

            if EPnew != ep[-1]:
                AFnew = min(0.2, af[-1] + 0.02)
            else:
                AFnew = af[-1]

        if direction[-1] == 1 and sar_curve[-1] + af[-1] * (EPnew - sar_curve[-1]) <= data_low[i]:
            direction.append(1)
            sar_curve.append(sar_curve[-1] + AFnew * (EPnew - sar_curve[-1]))
            ep.append(EPnew)
            af.append(AFnew)
        else:
            if direction[-1] == 1 and sar_curve[-1] + af[-1] * (EPnew - sar_curve[-1]) > data_low[i]:
                if data_low[i] >= sar_curve[-1]:
                    direction.append(1)
                    sar_curve.append(data_low[i])
                    ep.append(EPnew)
                    af.append(AFnew)
                else:
                    direction.append(-1)
                    sar_curve.append(max(data_high[i], ep[-1]))
                    ep.append(min(data_low[i], data_low[i - 1]))
                    af.append(0.02)

            else:
                if direction[-1] == -1 and sar_curve[-1] - af[-1] * (sar_curve[-1] - EPnew) >= data_high[i]:
                    direction.append(-1)
                    sar_curve.append(sar_curve[-1] - af[-1] * (sar_curve[-1] - EPnew))
                    ep.append(EPnew)
                    af.append(AFnew)
                else:
                    if direction[-1] == -1 and sar_curve[-1] - af[-1] * (sar_curve[-1] - EPnew) < data_high[i]:
                        if data_high[i] <= sar_curve[-1]:
                            direction.append(-1)
                            sar_curve.append(data_high[i])
                            ep.append(EPnew)
                            af.append(AFnew)
                        else:
                            direction.append(1)
                            sar_curve.append(min(data_low[i], ep[-1]))
                            ep.append(max(data_high[i], data_high[i - 1]))
                            af.append(0.02)

    df_temp = pd.DataFrame({'mts': pd.Series(mts_data),
                            'SAR': pd.Series(sar_curve),
                            'EP': pd.Series(ep),
                            'AF': pd.Series(af),
                            'direction': pd.Series(direction)
                            })
    df_temp['mts'] = pd.to_datetime(df_temp['mts'], unit='s')
    df_temp = df_temp.set_index(['mts'])

    return df_temp
