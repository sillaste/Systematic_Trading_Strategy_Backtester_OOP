import yaml
from utils import *
import strategies as strategy
import backtest as backtest
import analysis as analysis
import time


#readme:
#The backtest is composed of different classes to provide genralizability and compartmentalization.
#The config.yaml centralizes the parameters used throughout the backtest. 
#The main.py file and function are used for running the backtester as well as specifying the arguments of the component classes.
#The analysis.py file holds the classes for processing the input data, logging transactions and processing the output data.
#The backtest.py file holds the actual event-driven backtester that performs the portfolio management.
#The strategies.py file holds the different investment strategies and the investment process for the strategies.
#The utils.py file contains utility functions which are helpful in performing certain calculations in the backtest. 


#Assumptions:
#1. No fractional shares.
#2. Smallest unit of option purchase is the contract size of 100.
#3. There is sufficient liquidity to purchase required stocks and options.
#4. The stock and options purchases do not affect their prices (i.e. no slippage or market impact).
#5. Options maturity are always month start/end to represent a more realistic backtest. Option availability at every day in the month is unlikely.
#6. Options are European with continuous dividends. This is not a true representation of reality as the options on the stock are American and options are paid discretely.




def main():

    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)

    timestr = time.strftime("%Y%m%d_%H%M%S")
    data_process = analysis.DataProcess(config['data_file'],interpolate_maturity=config['data']['interpolate_maturity'],interpolate_interest_rate=config['data']['interpolate_interest_rate'])
    
    for strategy_name in config['strategy_names']:
        transaction_log = analysis.Transactions(data_process)
        if strategy_name == 'Buy_And_Hold':
            strat = strategy.BuyandHoldStrategy(data_process,transaction_log,stock_name = config['stock_name'],transaction_costs = config['transaction_costs']['stock'])
        if strategy_name == 'Trend':
            strat = strategy.TrendStrategy(data_process,transaction_log,stock_name = config['stock_name'], short_average = config['trend']['short_average'], long_average = config['trend']['long_average']
            ,transaction_costs = config['transaction_costs']['stock'])
        if strategy_name == 'Collar':
            strat = strategy.CollarStrategy(data_process,transaction_log,stock_name = config['stock_name'], call_strike = config['collar']['call_strike'],call_maturity = config['collar']['call_maturity']
            ,put_strike = config['collar']['put_strike'],put_maturity = config['collar']['put_maturity'],contract_size = config['collar']['contract_size']
            ,cash_buffer_percent = config['collar']['cash_buffer_percent'])
        
        backtester = backtest.BackTest(data_process,strat,transaction_log,stock_name = config['stock_name'], starting_balance = config['starting_balance'])
        results = analysis.Analysis(data_process,transaction_log,backtester,strategy_name = strategy_name, directory = config['analysis']['directory'],timestr = timestr)
        results.plot_mv()
        results.display_transactions()
        results.performance_metrics()

if __name__ == '__main__':
    main()
