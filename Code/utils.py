import numpy as np
import scipy.stats as stats

#Function: Equation for price of a European call/put option in the Black Scholes model with continious dividends
def BlackScholes(S,T_Mat,t,K,sigma,r,q,option_type):
    tau = T_Mat - t
    F = S * np.exp((r-q)*tau)
    d1 = 1/(sigma * np.sqrt(tau)) * (np.log(S/K)+(r-q+ (1/2) * sigma ** 2)*tau)
    d2 = d1 - sigma * np.sqrt(tau)
    if option_type == 'call':
        C_P = np.exp(-r*tau) * (F * stats.norm.cdf(d1) - K*stats.norm.cdf(d2))
    elif option_type == 'put':
        C_P = np.exp(-r*tau) * (K * stats.norm.cdf(-d2) - F*stats.norm.cdf(-d1))
    else:
        raise Exception("Please input a valid option type.")
    return C_P

#Function: Payoff of a call/put option at expiry
def OptionPayoff(S,K,option_type):
    if option_type == 'call':
        payoff = max(S-K,0)
    elif option_type == 'put':
        payoff = max(K-S,0)
    else:
        raise Exception("Please input a valid option type.")
    return payoff

#Function: Find nearest integer to x that is divisible by y. 
#Used in collar strategy for ensuring numnber of stocks purchased can be evenly split between all put option contracts.
def nearest_divisible(x, y):    
    near_multiple = round(x / y)
    closest_number = near_multiple * y
    return closest_number
