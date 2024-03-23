# Systematic_Trading_Strategy_Backtester_OOP
The coding project is a general event-driven back-testing framework that can test various trading or allocation strategies.
The backtest is composed of different classes to provide generalizability and compartmentalization.

The contents of the files are as follows:
The config.yaml centralizes the parameters used throughout the backtest.
The main.py file and function are used for running the backtester as well as specifying the arguments of the component classes.
The analysis.py file holds the classes for processing the input data, logging transactions and processing the output data.
The backtest.py file holds the actual event-driven backtester that performs the portfolio management.
The strategies.py file holds the different investment strategies and the investment process for the strategies.
The utils.py file contains utility functions which are helpful in performing certain calculations in the backtest.
The Coding_Proj_Data.xls file contains the price of the SPY as well as other information related to the security such as dividends and implied volatility for options pricing.
