import numpy as np
import pandas as pd 
from utils import *


#Class: Buy and hold strategy. Put all cash into the stock and never sell. Used for comparison against the trend and collar strategies.
class BuyandHoldStrategy:

    def __init__(self,data_process,transactions,**kwargs):
        self.data_process = data_process    
        self.transaction_type = transactions
        self.kwargs = kwargs
        self.stock_name = self.kwargs['stock_name']
        self.transaction_costs = self.kwargs['transaction_costs']

    #Always check if there is cash that can be invested.
    def signal(self,date):
            return 1

    #Any cash is immediatley invested into the stock.
    def rebalance(self,signal,date,current_price, holdings, cash): 
        purchase = max(cash // (current_price + self.transaction_costs),0)
        holdings[self.stock_name] = purchase + holdings.get(self.stock_name,0) 
        cash -= purchase * (current_price + self.transaction_costs)
        if purchase > 0 :
            self.transaction_type.log_transaction(date,self.stock_name, purchase,current_price,'Buy')
            self.transaction_type.log_transaction(date,self.stock_name, purchase,self.transaction_costs,'Transaction Costs')
        portfolio_value = holdings.get(self.stock_name,0)*current_price + cash
        return holdings, portfolio_value, cash

#Class: Trend Strategy. When the simple moving average (SMA) 50-day crosses above the SMA 200-day invest all cash in stock.
#If the SMA 50-day crosses below SMA 200-day sell all stock if holding any.
class TrendStrategy:

    def __init__(self, data_process, transactions, **kwargs):
        self.data_process = data_process
        self.transaction_type = transactions
        self.kwargs = kwargs
        self.stock_name = self.kwargs['stock_name']
        self.short_average = self.kwargs['short_average']
        self.long_average = self.kwargs['long_average']
        self.transaction_costs = self.kwargs['transaction_costs']

    #Function: Calculate the signal if we should invest all cash in stock or sell all stock or do nothing.
    def signal(self,date):
        prices = self.data_process.get_prices()
        date_index = prices.index.get_loc(date)
        #Need to have historical data as far back as longest average so that a proper signal can be calculated.
        if prices.loc[:date].shape[0] <= self.long_average+1:
            print("Not Enough Data to Generate Signal,", "Date:", date)
            return 0
        
        #Calculate SMA 50-day & 200-day for current and previous day.
        #if they are the same do nothing as there was no crossing. If they are different either buy or sell all stock depending on crossing direction.
        current_signal = self.sma(prices,date_index)
        previous_signal = self.sma(prices,date_index-1)

        if current_signal == previous_signal:
            return 0
        else:
            return current_signal
    
    #Function: Calculate SMA 50-day and SMA 200-day. Determine which SMA is greater than the other.
    def sma(self,prices,date_index):
        short_sma = prices.loc[:,'Price'].iloc[date_index-self.short_average:date_index].mean()
        long_sma = prices.loc[:,'Price'].iloc[date_index-self.long_average:date_index].mean()
        
        if short_sma > long_sma:
            signal = 1
        else:
            signal = -1
        return signal
    
    #Function: After knowing whether to buy or sell, calculate the amount of stock held and cash balance.
    #Log the transactions and calculate the portfolio value.
    def rebalance(self,signal,date,current_price, holdings, cash):
        if signal == 1:
            #Invest maximum amount cash into stock while being aware of transaction costs.
            holdings[self.stock_name] = max(cash // (current_price + self.transaction_costs),0)
            cash -= holdings[self.stock_name] * (current_price + self.transaction_costs)
            self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],current_price,'Buy')
            self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],self.transaction_costs,'Transaction Costs')
        elif signal == -1:
            cash += holdings.get(self.stock_name,0) * (current_price - self.transaction_costs)
            if holdings.get(self.stock_name,0) > 0:
                self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],current_price,'Sell')
                self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],self.transaction_costs,'Transaction Costs')
            holdings[self.stock_name] = 0
        portfolio_value = holdings.get(self.stock_name,0)*current_price + cash
        return holdings, portfolio_value, cash



#Class: Collar Strategy. Invest into stock and sell 1 month call options with a 105% strike that fully covers stock notional.
# As well as, buy 3,6,9 and 12 month put options with 95% strike that are evenly distributed and fully cover stock notional.
#Roll options at option expiry to maintain coverage on the stock.
#Strategy has been organized to allow for multiple maturities for both calls and puts if needed.
class CollarStrategy:
    
    def __init__(self,data_process,transactions,**kwargs):
        self.data_process = data_process
        self.transaction_type = transactions
        self.kwargs = kwargs
        self.stock_name = self.kwargs['stock_name']
        call_strike = self.kwargs['call_strike']
        call_maturity = self.kwargs['call_maturity']
        put_strike = self.kwargs['put_strike']
        put_maturity = self.kwargs['put_maturity']
        self.transaction_costs = {self.stock_name : 0.03, 'call' : 0.04, 'put' : 0.04}
        self.option_strike = {'call' : call_strike, 'put': put_strike}
        self.option_maturity = {'call' : call_maturity, 'put' :put_maturity}
        self.all_option_maturity_dates = {'call' : None, 'put' : None} #Container for all option maturity dates throughout the back test.
        self.option_maturity_dates = {'call' : {}, 'put' : {}} #Container for current options held maturity dates.
        self.option_strike_price = {'call' : {}, 'put': {}} #Actual strike price when entering into the option.
        self.option_initial_price = {'call' : {}, 'put': {}} #Price of option when entering into the contract.
        self.option_purchase_structure = {'call' : {'buy' : 1, 'sell' : -1}, 'put': {'buy' : -1, 'sell' : 1}} #Indicates short selling payoff for calls and long payoff for puts.
        #Cash buffer size to provide extra cash when rolling options. Helps to prevent needing to sell stock when rolling options.
        self.cash_buffer_percent = kwargs['cash_buffer_percent']
        #Contract size for options.
        self.contract_size = kwargs['contract_size']
        
        self.process_maturity_dates()

    #Get all option maturity dates based on the beginning of the month.
    #Using only start/end of month allows for easier option maturity management.
    def process_maturity_dates(self):
        dates = self.data_process.get_prices().index

        for option in self.option_maturity.keys():
            for mat in self.option_maturity[option]:
                cur_date = dates.min()
                end_date = dates.max()
                option_dates = []
                while cur_date < end_date:
                    option_dates.append(cur_date)
                    cur_date = cur_date + pd.offsets.Day(mat)
                    prev_date = cur_date - pd.offsets.Day(1)

                    #Since implied vols/option maturity is not exactly monthly,
                    #there can be times where the calculation of maturity dates gets stuck in a loop.
                    #This prevents this infinite loop from occuring.
                    if prev_date.month == cur_date.month:
                        if cur_date.day <= 15:
                            cur_date -= pd.offsets.MonthBegin(1)
                        else:
                            cur_date += pd.offsets.MonthBegin(1)
                option_dates.append(cur_date)
                if self.all_option_maturity_dates[option] is None:
                    self.all_option_maturity_dates[option] = pd.Series(option_dates)
                else:
                    self.all_option_maturity_dates[option] = pd.concat([self.all_option_maturity_dates[option],pd.Series(option_dates)])
            self.all_option_maturity_dates[option] = pd.DatetimeIndex(self.all_option_maturity_dates[option].values).unique()

    #Function: Determines when stocks/options should be purchased or rolled.
    #stocks/options should be purchased on first day with available implied vol data.
    #options should be rolled at the respective options expiry date.
    def signal(self,date):
        prices = self.data_process.get_prices()
        implied_vol = self.data_process.get_implied_vol()
        if implied_vol[str(self.option_maturity['call'][0]) + "IV"].loc[date,self.option_strike['call']] == 0:
            print('No Implied Volatility Data For This Date. Cannot Generate Signal,', 'Date:', date)
            return -1
        
        for option in self.all_option_maturity_dates.keys():
            if date in self.all_option_maturity_dates[option]:
                return 1
        
        return 0


    #Function: Stock and Option purchasing as well as rolling options. The function has three sections.
    #1. At the start of the backtest, buy the stock and enough options to cover the stock.
    #2. Roll the options and if needed sell stock to fund the option roll over.
    #3. Calculate the current value of the portfolio.
    def rebalance(self,signal,date,current_price,holdings,cash):
        
        #No implied vol data so can not execute strategy.
        if signal == -1:
            return holdings, cash, cash

        option_price = {'call' : {}, 'put': {}} #current price of the option
        option_payoff = {'call' : 0, 'put': 0} #option payoff after excerising
        option_rebalance = {'call' : False, 'put': False} #which option type should be rolled
        option_transaction = {'call' : 0, 'put': 0} #Store cost when buy/selling options
        option_expired_holdings = {'call' : 0, 'put': 0} #store holdings of options expiring at the current date
        first_maturity = {'call' : 0, 'put': 0} #store first maturity of option series (i.e. put, 90)
        last_maturity = {'call' : 0, 'put': 0} #store last maturity of option series. (i.e. put, 360)
        option_emergency_trasaction = 0 #store cost when buy/sell options in emergency rebalance


        
        start_date = self.data_process.get_implied_vol()[str(self.option_maturity['call'][0]) + "IV"]
        start_date = start_date.loc[start_date.loc[:,self.option_strike['call']] != 0].index[0]
        #Section 1. Buy stocks. As well as options to cover stock.
        if date == start_date:
            for option in option_price.keys():
                holdings[option] = {}
                for mat in self.option_maturity[option]:
                    self.option_strike_price[option][mat] = self.option_strike[option]*current_price
                    option_price[option][mat] = BlackScholes(current_price,mat/365,0,self.option_strike_price[option][mat], self.data_process.get_implied_vol()[str(mat) + "IV"].loc[date,self.option_strike[option]], self.data_process.get_interest_rates().loc[date,mat],self.data_process.get_prices().loc[date,'12M Div Yield'],option)
                    self.option_maturity_dates[option][mat] = self.all_option_maturity_dates[option][self.all_option_maturity_dates[option].get_loc(date + pd.offsets.Day(mat),method='nearest')]
                    self.option_initial_price[option][mat] = option_price[option][mat]
                #Cost to long/short the options.
                option_transaction[option] = self.option_purchase_structure[option]['buy'] * np.average(list(self.option_initial_price[option].values())) - self.transaction_costs[option]*np.average(list(self.option_initial_price[option].values()))
            
            #The maximum amount of stock that can be purchased while ensuring the options on the collar strategy can be properly executed.
            #As well as maintaining a capital reserve of 10% of the starting balance after all transactions to be used as a liquidity buffer when rolling options.
            holdings[self.stock_name] = (1-self.cash_buffer_percent)*cash // ((current_price+self.transaction_costs[self.stock_name]) - sum([option_transaction[option] for option in option_transaction.keys()]))
            
            #Find the nearest number lower than this amount of stock we want to purchase that is a multiple of the option contract size (100) and can be split evenly among all put option maturities.
            holdings[self.stock_name] = nearest_divisible(holdings[self.stock_name] // self.contract_size,max([len(self.option_maturity[option]) for option in option_price.keys()])) * self.contract_size
            
            self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],current_price,'Buy')
            self.transaction_type.log_transaction(date,self.stock_name, holdings[self.stock_name],self.transaction_costs[self.stock_name],'Transaction Costs')
            
            cash -= holdings[self.stock_name]*(current_price + self.transaction_costs[self.stock_name])

            for option in option_price.keys():
                for mat in self.option_maturity[option]:
                    #only purchase option amounts that will cover the stock and is in multiples of the contract size.
                    holdings[option][mat] = ((holdings[self.stock_name] // len(self.option_maturity[option])) // self.contract_size) * self.contract_size
                    self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,mat), holdings[option][mat],option_price[option][mat],'Buy')
                    self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,mat), holdings[option][mat],self.transaction_costs[option],'Transaction Costs')
                    cash += holdings[option][mat]*(self.option_purchase_structure[option]['buy']*option_price[option][mat] - self.transaction_costs[option])


        #Section 2. Rebalance/roll options.
        elif signal == 1:
            
            #Check which option types need to be rolled.
            for option in self.all_option_maturity_dates.keys():
                if date in self.all_option_maturity_dates[option]:
                    option_rebalance[option] = True
                    
            
            
            for option in option_price.keys():
                if option_rebalance[option]:
                    first_maturity[option] = self.option_maturity[option][0]
                    last_maturity[option] = self.option_maturity[option][-1]

                    option_payoff[option] = OptionPayoff(current_price, self.option_strike_price[option][first_maturity[option]], option)
                    option_expired_holdings[option] = holdings[option][first_maturity[option]]

                    #Roll option maturities (eg. 12-month becomes 9 month, 9 month becomes 6 month etc.)
                    for mat, next_mat in zip(self.option_maturity[option][:-1],self.option_maturity[option][1:]):
                        self.option_strike_price[option][mat] = self.option_strike_price[option][next_mat]
                        self.option_initial_price[option][mat] = self.option_initial_price[option][next_mat]
                        self.option_maturity_dates[option][mat] = self.option_maturity_dates[option][next_mat] 
                        holdings[option][mat] = holdings[option][next_mat] 
                    
                    self.option_strike_price[option][last_maturity[option]] = self.option_strike[option]*current_price
                    self.option_initial_price[option][last_maturity[option]] =  BlackScholes(current_price,last_maturity[option]/365,0,self.option_strike_price[option][last_maturity[option]], self.data_process.get_implied_vol()[str(last_maturity[option]) + "IV"].loc[date,self.option_strike[option]], self.data_process.get_interest_rates().loc[date,last_maturity[option]],self.data_process.get_prices().loc[date,'12M Div Yield'],option)
                    self.option_maturity_dates[option][last_maturity[option]] = self.all_option_maturity_dates[option][self.all_option_maturity_dates[option].get_loc(date + pd.offsets.Day(last_maturity[option]),method='nearest')]
                    #How many options need to be purchased to maintain full coverage of the stock holdings. 
                    holdings[option][last_maturity[option]] = (max(holdings[self.stock_name]-sum([holdings[option].get(mat,0) for mat in self.option_maturity[option][:-1]]),0) // self.contract_size) * self.contract_size
                    #Cost to buy and roll options
                    option_transaction[option] = self.option_rebalance_cost(holdings, option_expired_holdings, option_payoff,last_maturity[option],option)

            #Required capital to roll options        
            required_balance = cash + sum([option_transaction[option] for option in option_transaction.keys()])
            

            

            #If the required capital is less than available cash then we need to sell stock.
            if required_balance < 0:
                print("Insufficient cash {} must be sold to reblance.".format(self.stock_name), 'Date:', date)
                #When selling stock, sell enough to replenish cash buffer based on stock holdings and price.
                required_balance += -self.cash_buffer_percent*holdings[self.stock_name]*current_price

                #Get current option prices which is used when rolling options
                for option in option_price.keys():
                    for mat in self.option_maturity[option]: 
                        option_present_time = max((mat - (self.option_maturity_dates[option][mat] - date).days)/365,0)
                        option_price[option][mat] = BlackScholes(current_price,mat/365,option_present_time,self.option_strike_price[option][mat], self.data_process.get_implied_vol()[str(mat) + "IV"].loc[date,self.option_strike[option]], self.data_process.get_interest_rates().loc[date,mat],self.data_process.get_prices().loc[date,'12M Div Yield'],option)
                
                #Cost from selling options
                option_emergency_rebalance_cost = 0
                for option in option_price.keys():
                    for mat in self.option_maturity[option]: 
                        option_emergency_rebalance_cost += self.option_purchase_structure[option]['sell']*(option_price[option][mat]) - self.transaction_costs[option]
                
                #Find the amount of stock to sell that will allow us to roll options and replenish cash buffer. 
                #Used ceiling divison to ensure we are always selling whole stocks and on the side of more than we need.
                stock_rebalance = -(-required_balance // (current_price - self.transaction_costs[self.stock_name] + option_emergency_rebalance_cost))
                #Make sure the amount of stock we are selling is never greater than what we hold in stock or what we hold in options. 
                holdings_quantity = []
                for option in option_price.keys():
                    for mat in self.option_maturity[option]: 
                        holdings_quantity.append(-holdings[option][mat]) 
                stock_rebalance = max(stock_rebalance, -holdings[self.stock_name], max(holdings_quantity))
            else:
                stock_rebalance = 0
            
            #Sell stock and adjust the amount of options we are rolling based on the new amount of stock held.
            if stock_rebalance != 0:
                previous_stock_holdings = holdings[self.stock_name]
                holdings[self.stock_name] = nearest_divisible((holdings[self.stock_name] + stock_rebalance) // self.contract_size,max([len(self.option_maturity[option]) for option in option_price.keys()])) * self.contract_size
                stock_rebalance = holdings[self.stock_name] - previous_stock_holdings
                self.transaction_type.log_transaction(date,self.stock_name, abs((stock_rebalance // self.contract_size) * self.contract_size),current_price,'Sell')
                self.transaction_type.log_transaction(date,self.stock_name, abs((stock_rebalance // self.contract_size) * self.contract_size),self.transaction_costs[self.stock_name],'Transaction Costs')
                for option in option_price.keys():
                    for mat in self.option_maturity[option]:
                        holdings[option][mat] += ((stock_rebalance // len(self.option_maturity[option])) // self.contract_size) * self.contract_size
            

            for option in option_price.keys():
                if option_rebalance[option]:                    
                    self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,last_maturity[option]),holdings[option][last_maturity[option]],self.option_initial_price[option][last_maturity[option]],'Buy')
                    self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,last_maturity[option]),holdings[option][last_maturity[option]],self.transaction_costs[option],'Transaction Costs')
                    if option_payoff[option] > 0:
                        self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,first_maturity[option]), option_expired_holdings[option],option_payoff[option],'Sell')
                        self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,first_maturity[option]), option_expired_holdings[option],self.transaction_costs[option],'Transaction Costs')
                if stock_rebalance != 0:
                    for mat in self.option_maturity[option][:-1]:
                        self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,mat),abs(stock_rebalance),option_price[option][mat],'Sell')
                        self.transaction_type.log_transaction(date,'{}, Maturity:{}'.format(option,mat),abs(stock_rebalance),self.transaction_costs[option],'Transaction Costs')
                        option_emergency_trasaction += abs(stock_rebalance)*(self.option_purchase_structure[option]['sell']*option_price[option][mat] - self.transaction_costs[option])

            cash += -1*stock_rebalance*(current_price - self.transaction_costs[self.stock_name]) + option_emergency_trasaction + sum([self.option_rebalance_cost(holdings,option_expired_holdings,option_payoff,last_maturity[option],option) for option in (option for option in option_rebalance.keys() if option_rebalance[option])])

        

        #Section 3. Determine portfolio value based on cash, stocks held and options held
        portfolio_value = holdings[self.stock_name]*current_price + cash                        
        for option in self.option_maturity.keys():
            for mat in self.option_maturity[option]:

                #Need to floor the option time to expiry at zero to account for difference in option maturity based on implied vols and month end dates.
                option_present_time = max((mat - (self.option_maturity_dates[option][mat] - date).days)/365,0)
                option_price[option][mat] = BlackScholes(current_price,mat/365,option_present_time,self.option_strike_price[option][mat], self.data_process.get_implied_vol()[str(mat) + "IV"].loc[date,self.option_strike[option]], self.data_process.get_interest_rates().loc[date,mat],self.data_process.get_prices().loc[date,'12M Div Yield'],option)
                portfolio_value += option_price[option][mat]*holdings[option][mat]
        
        return holdings, portfolio_value, cash


    #Provides the payoff from excerising the option and rolling/entering into a new option contract.
    def option_rebalance_cost(self,holdings,option_expired_holdings,option_payoff,last_maturity,option):
        roll_option = holdings[option].get(last_maturity,0)*(self.option_purchase_structure[option]['buy']*self.option_initial_price[option][last_maturity] - self.transaction_costs[option])
        if option_payoff[option] == 0:
            exercise_trans_cost = 0
        else:
            exercise_trans_cost = -self.transaction_costs[option]*option_expired_holdings[option]
        exercise_option = option_expired_holdings[option]*self.option_purchase_structure[option]['sell']*option_payoff[option] + exercise_trans_cost
        return  roll_option + exercise_option
