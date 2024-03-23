import numpy as np
import pandas as pd
import scipy.interpolate as interp
import matplotlib.pyplot as plt
import os



#Class: Read and process stock data so it can be used for back testing investment strategies. 
class DataProcess:
    def __init__(self,file,**kwargs):
        self.file = file

        self.prices = None
        self.dividends = None
        self.interest_rates = None
        self.implied_vol = {}
        self.kwargs = kwargs

        self.load_data()

    #Function: Load the tabs in the excel file and organize them into categories.
    def load_data(self):
        stock_data = pd.ExcelFile(self.file)
        self.prices = pd.read_excel(stock_data, sheet_name='Price', index_col = 0, parse_dates=True)
        self.dividends = pd.read_excel(stock_data, sheet_name='Dividend', index_col = 0, parse_dates=['Date','ExDate','RecordDate','PayDate'])
        self.interest_rates = pd.read_excel(stock_data, sheet_name='Interest Rate', index_col = 0, header = 1, parse_dates=True)
        implied_vol_list = ['30IV', '60IV','90IV','180IV','360IV']
        for iv in implied_vol_list:
            self.implied_vol[iv] = pd.read_excel(stock_data, sheet_name=iv, index_col = 0, header = 1, parse_dates=True)
        
        self.clean_data()

    #Function: Organize dividends and implied vols index to have same index as stock prices.
    #Implied vols are missing first 10 days of data.
    def clean_data(self):
        self.prices = self.prices.dropna(axis=1)
        self.dividends = self.dividends.reindex(self.prices.index)
        for iv in self.implied_vol.keys():
            self.implied_vol[iv] = self.implied_vol[iv].reindex(self.prices.index, fill_value = 0)
        
        self.interpolate_data()

    #Function: Interpolate required data for back test strategies.
    #Interpolate 9 month implied vol and interest rates for put options in collar strategy.
    def interpolate_data(self):
        interpolate_maturity = self.kwargs['interpolate_maturity']
        #Interpolate implied vol.
        implied_vol_maturity = [int(iv_mat[:-2]) for iv_mat in self.implied_vol.keys()]
        interpolate_iv = pd.DataFrame(data = 0, index = self.implied_vol['30IV'].index, columns = self.implied_vol['30IV'].columns)
        #Need to interpolate implied vols across maturities for the same strike so we need to reformat the implied vol in the format (strike x maturity) for each date.
        for date in interpolate_iv.index:
            interpolate_date = np.zeros((interpolate_iv.shape[1],len(self.implied_vol)))
            for j,iv in enumerate(self.implied_vol.keys()):
                interpolate_date[:,j] = self.implied_vol[iv].loc[date].values
            for strike, iv_per_strike in enumerate(interpolate_date):

                interpolate_iv.loc[date,interpolate_iv.columns[strike]] = np.interp(interpolate_maturity,implied_vol_maturity,iv_per_strike)
        self.implied_vol[str(interpolate_maturity)+"IV"] = interpolate_iv

        interpolate_interest_rate = self.kwargs['interpolate_interest_rate']
        #Interpolate interest rate. There is an error in the 7 day and 60 day interest rates. They remain constant over the 2022-2023 rate hike cycle.
        interpolate_ir = pd.DataFrame(data = 0, index = self.interest_rates.index, columns = [interpolate_interest_rate])
        for date in interpolate_ir.index:
            interpolate_ir.loc[date,interpolate_interest_rate] = np.interp(interpolate_interest_rate, self.interest_rates.columns.to_numpy(),self.interest_rates.loc[date].values)
        self.interest_rates = pd.concat([self.interest_rates,interpolate_ir],axis=1)

        self.convert_percent()

    #Function: Convert dividend yields, interest rates and implied vol from percentages to actual value, this makes it easier when performing calculations.
    def convert_percent(self):
        denominator = 100
        self.prices['12M Div Yield'] /= denominator
        self.interest_rates /= denominator
        for iv in self.implied_vol.keys():
            self.implied_vol[iv] /= denominator

    #The following functions are used to get stock data from the DataProcess class.
    def get_prices(self):
        return self.prices

    def get_dividends(self):
        return self.dividends
    
    def get_interest_rates(self):
        return self.interest_rates
    
    def get_implied_vol(self):
        return self.implied_vol


#Class: Creates a log for each transaction
class Transactions:

    def __init__(self, data_process):
        self.data_process = data_process
        self.transactions = []

    def log_transaction(self,date,asset,quantity,price,transaction_type):
        self.transactions.append([date,asset,quantity,price,transaction_type])

    def get_log(self):
        self.transactions = np.array(self.transactions)
        self.transactions_frame = pd.DataFrame(data = self.transactions[:,1:],index = self.transactions[:,0], columns = ['Asset', 'Quantity', 'Price', 'Transaction Type'])
        return self.transactions_frame

#Class: Analyze Backtest Results
class Analysis:

    def __init__(self,data_process,transactions,backtest, **kwargs):
        self.data_process = data_process
        self.transactions = transactions
        self.backtest = backtest
        self.kwargs = kwargs
        self.strategy_name = self.kwargs['strategy_name']
        self.timestr = self.kwargs['timestr']
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.directory = kwargs['directory']
        self.directory = str(dir_path)+self.directory+self.timestr+'/'+self.strategy_name
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

    def plot_mv(self):
        portfolio_value = self.backtest.get_portfolio_value_frame()
        portfolio_value.plot()
        plt.xlabel('Date')
        plt.ylabel('Portfolio Value ($)')
        plt.title('{} {} {}'.format(self.strategy_name, 'Strategy', 'Portfolio Value'))
        plt.savefig('{}/{}.png'.format(self.directory,self.strategy_name))          
        plt.show()

    def display_transactions(self):
        print('Transactions {} Strategy : '.format(self.strategy_name), self.transactions.get_log())
        self.transactions.get_log().to_csv('{}/Transaction_Log_{}.csv'.format(self.directory,self.strategy_name))

    def performance_metrics(self):
        metrics = {}
        #Returns Metrics
        portfolio_value = self.backtest.get_portfolio_value_frame()
        terminal_value = portfolio_value.iloc[-1]
        portfolio_return = portfolio_value.pct_change().dropna()
        cumulative_return = (1+portfolio_return).prod()-1
        annualized_return = (1+cumulative_return) ** (365/(portfolio_value.index[-1] - portfolio_value.index[0]).days) -1
        annualized_volatility = portfolio_return.std() * np.sqrt(365)
        
        #Excess Return Metrics
        daily_interest_rates = (1+self.data_process.get_interest_rates().loc[:,1])** (1/365) - 1
        cumulative_excess_return = (1+portfolio_return-daily_interest_rates).prod()-1
        annualized_excess_return = (1+cumulative_excess_return) ** (365/(portfolio_value.index[-1] - portfolio_value.index[0]).days) -1
        annualized_excess_return_volatility = (portfolio_return - daily_interest_rates).std() * np.sqrt(365)
        sharpe_ratio = annualized_excess_return / annualized_excess_return_volatility

        #Drawdown Metrics
        drawdowns = pd.Series(0,index=portfolio_value.index)
        for date in portfolio_value.index:
            drawdowns.loc[date] = ((portfolio_value.loc[:date]).max()-portfolio_value.loc[date])/(portfolio_value.loc[:date]).max()

        max_drawdown = drawdowns.max()
        max_drawdown_date = drawdowns.idxmax()
        quantile_loss = portfolio_return.quantile(q=0.05)

        #Transaction Metrics
        transactions = self.transactions.get_log()
        turnover = (transactions.loc[transactions['Transaction Type'].str.contains('Buy|Sell')]['Quantity']).sum()
        transaction_costs = transactions.loc[transactions['Transaction Type'] == 'Transaction Costs']
        total_transaction_costs = (transaction_costs['Price']).T.dot(transaction_costs['Quantity'])
        

        metrics['Terminal Value'] = terminal_value
        metrics['Annualized Excess Return'] = annualized_excess_return
        metrics['Annualized Excess Return Volatility'] = annualized_excess_return_volatility
        metrics['Sharpe Ratio'] = sharpe_ratio
        metrics['Maximum Drawdown'] = max_drawdown
        metrics['Turnover Quantity'] = turnover
        metrics['Transaction Costs'] = total_transaction_costs

        metrics_frame = pd.DataFrame(metrics.items(),columns=['Performance Metric', 'Value'])
        metrics_frame.to_csv('{}/Metrics_{}.csv'.format(self.directory,self.strategy_name),index=False)





        
    
