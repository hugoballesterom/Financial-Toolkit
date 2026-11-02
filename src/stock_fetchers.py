import yfinance as yf
import finnhub as fn
from datetime import datetime, date
import numpy as np
import pandas as pd

def yahoo_stock_fetcher(tickers, start_date, end_date): #el fetcher recibe una lista con los tickers que tiene que buscar y las fechas de start y end
    raw_data= yf.download(tickers, start=start_date, end=end_date, auto_adjust=False)
    raw_data = raw_data.rename(columns={"Open":"open","Adj Close":"adjusted_close","High":"high","Low":"low","Volume":"volume"}, level="Price") #cambiamos el nombre a las columnas para que correspondan a lo que pide PriceSeries

    names = {} #creamos un diccionario {ticker: nombre del ticker}
    normalized_data = {} #creamos un diccionario {ticker: dataframe del ticker}

    for ticker in tickers:
        names[ticker] = yf.Ticker(ticker).info["longName"]
        ticker_data = raw_data.xs(ticker, axis =1, level= 'Ticker').drop(columns=["Close"])#filtra las columnas por el nivel Ticker y extrae solo los datos del activo indicado. la segunda parte elimina la columna de 'close'
        normalized_data[ticker]=ticker_data #en los diccionarios no hay .append() se pone dictname[key]=valor

    return names, normalized_data #devolvemos los diccionarios 

def tiingo_stock_fetcher(tickers_start_date, end_date): #el fetcher recibe una lista con los tickers que tiene que buscar y las fechas de start y end
    return

yahoo_stock_fetcher(['AAPL', 'TSLA'],"2025-01-01","2026-01-01" )

ticker: aapl type: stock api: yahoo