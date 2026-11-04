from dataclasses import dataclass
from datetime import datetime, date
import pandas as pd
import numpy as np


@dataclass
class Fundamentals:
    balance_sheet: pd.DataFrame
    income_statement: pd.DataFrame
    cash_flow: pd.DataFrame

@dataclass
class PriceSeries:
    data: pd.DataFrame #date, open, adjusted close, high, low, volume, 
   
    def current_price(self): #metodo que calcula el precio actual de hoy 
        return self.data['adjusted_close'].iloc[-1] #utilizamos iloc porque filtra por posicion no por indice
        
    def compute_return(self): #metodo que calcula el retorno logaritmico diario del activo en decimal
        return np.log(self.data["adjusted_close"] / self.data["adjusted_close"].shift(1)) # me devuelve una serie de pandas

    def cumulative_return(self): #método que calcula el retorno total acumulado en el periodo indicado
        return np.exp(self.compute_return().sum()) - 1 # sumamos todos los retornos logaritmicos y aplicamos la exponencial para obtener la rentabilidad acumulada

    def compute_mean_return(self): #metodo que calcula la media de los retornos del activo
        return self.compute_return().mean() #como compute_return es un método pongo () # como no depende de data sino de la serie de retornos pongo compute_return()

    def compute_volatility(self): #metodo que calcula la volatilidad del activo en funcion de los retornos
        return self.compute_return().std() #formula de la desviacion tipica con todos los elementos de la serie de retornos
    
    def max_price(self): #metodo que calcula el precio maximo historico en la serie de adjusted_close
        return self.data["adjusted_close"].max()

    def min_price(self): #metodo que calcula el precio minimo historico en la serie de adjusted_close
        return self.data["adjusted_close"].min()

@dataclass
class BondSeries:
    data: pd.DataFrame # date, clean_price, accrued_interest, dirty_price, coupon_payment

    def current_clean_price (self): #metodo que calcula el último precio disponible
        return self.data['clean_price'].iloc[-1] #filtramos el dataframe de self por la columna de clean price usando iloc[-1]
    
    def current_dirty_price (self): #metodo que calcula el último precio disponible
        return self.data['dirty_price'].iloc[-1] #filtramos el dataframe de self por la columna de dirty price usando iloc[-1]

    def compute_bond_return (self): #metodo que calcula el retorno logaritmico diario del bono teniendo en cuenta la variacion del dirty price y el pago de cupones
        return np.log((self.data['dirty_price']+self.data['coupon_payment'])/self.data['dirty_price'].shift(1)) # 

    def bond_cumulative_return (self): #metodo que calcula el retorno acumulado de los bonos
        return np.exp(self.compute_bond_return().sum())-1 #

    def bond_mean_return (self):
        return self.compute_bond_return().mean()

    def bond_volatility(self):
        return self.compute_bond_return().std()

    def dirty_price_max(self):
        return self.data['dirty_price'].max()
    
    def clean_price_max(self):
        return self.data['clean_price'].max()

    def dirty_price_min(self):
        return self.data['dirty_price'].min()
        
    def clean_price_min(self):
        return self.data['clean_price'].min()

@dataclass
class FinancialAsset:
    ticker: str
    name: str


@dataclass
class Stock(FinancialAsset):
    price_series: PriceSeries
    fundamentals: Fundamentals


@dataclass
class Index(FinancialAsset):
    price_series: PriceSeries
    holdings_x_weight: pd.DataFrame


@dataclass
class Crypto(FinancialAsset):
    price_series: PriceSeries


@dataclass
class Bond(FinancialAsset):
    Bond_Series: BondSeries
    issuer: str
    nominal: float
    coupon: float
    ytm: float
    maturity: date


@dataclass
class Macroeconomy:
    country_code: str
    date: date
    inflation: float
    interest_rate: float
    gdp_growth: float
    unemployment_rate: float
