import numpy as np
import pandas as pd

#Class: Runs the event-driven back test and executes the desired trading strategy.
class BackTest:
    def __init__(self, data_process, strategy, transactions, **kwargs):
        self.data_process = data_process
        self.strategy = strategy
        self.kwargs = kwargs
        self.stock_name = self.kwargs['stock_name']
        self.cash = self.kwargs['starting_balance']
        self.transactions = transactions
        self.holdings = {}
        self.portfolio_value = {}
        self.dividend_pay_date = np.NaN
        self.dividend_payment = {}
        self.portfolio_value_frame = pd.Series(data= 0, index = self.data_process.get_prices().index)

        
        self.backtest()

    #Function: Loop through each date and perform the necessary portfolio management procedures.
    def backtest(self):
        prices = self.data_process.get_prices()
        for date in prices.index:
            current_price = prices.loc[date,'Price']
            signal = self.strategy.signal(date)
            self.rebalance(signal,date,current_price)
            self.portfolio_value -= self.cash
            self.dividends(date)
            self.interest(date)
            self.portfolio_value = self.cash + self.portfolio_value
            self.portfolio_value_frame.loc[date] = self.portfolio_value

    #Function: Rebalance the portfolio based on the trading strategy
    def rebalance(self,signal,date,current_price):
        self.holdings, self.portfolio_value, self.cash = self.strategy.rebalance(signal,date,current_price, self.holdings, self.cash)
    
    #Function: Determine dividends received from owning stock.
    def dividends(self,date):
        dividends = self.data_process.get_dividends()
        
        #Get dividend amount and date for upcoming dividend and the stock holdings just before the Ex-Date.
        if pd.notnull(dividends.loc[date,'ExDate']):
            self.dividend_pay_date = dividends.loc[date,'PayDate']
            self.dividend_payment = {'Quantity' : self.holdings, 'Price' : dividends.loc[date,'Amount']}

        if date == self.dividend_pay_date:
            self.cash += self.dividend_payment['Quantity'].get(self.stock_name,0)*self.dividend_payment['Price']
            if self.dividend_payment['Quantity'].get(self.stock_name,0) > 0:
                self.transactions.log_transaction(date,self.stock_name,self.dividend_payment['Quantity'].get(self.stock_name,0),self.dividend_payment['Price'],'Dividend')
    
    #Function: Collect overnight interest rate on cash. Overnight rate is used so cash can be quickly deployed if needed.
    def interest(self,date):
        self.cash *= (1+self.data_process.get_interest_rates().loc[date,1])**(1/365)
    

    def get_portfolio_value_frame(self):
        return self.portfolio_value_frame


