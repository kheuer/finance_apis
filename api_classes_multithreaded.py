# -*- coding: utf-8 -*-
"""
Created on Thu Jun  3 10:13:10 2021

@author: kheuer
"""
# total shares is actually shares outstanding
# Documentation is at: https://financialmodelingprep.com/developer/docs/
# Date format is always: "YYYY-MM-DD" e.g. "2021-11-08"

import time
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from api.api_classes import FinancialModelingPrep as FinancialModelingPrep_single

class InvalidResponse(Exception):
    def __init__(self, message):
        self.message = message
        #if "apikey" in message:
        #    i = message.index("apikey")
        #    key = message[i+7:i+39]
        #    self.message = message.replace(key, "xxxxxxxxxxxxxxxxxxx")
        
        super().__init__(self.message)

class FinancialModelingPrep:
    def __init__(self, api_key, limit_per_second):
        self.limit_per_second = limit_per_second
        self.api_key = api_key
        self.single = FinancialModelingPrep_single(self.api_key)
        self.base_path = "https://financialmodelingprep.com/api"
    
    def make_request(self, url):
        response = requests.request("GET", url).json()
        if not response:
            raise InvalidResponse(f"Invalid Response from API for url <{url}>")
        elif "Error Message" in response:
            raise InvalidResponse(response["Error Message"])
        
        return response
    
    def str_to_unix(self, time_str):
        time_str = time_str[:10]
        epoch = datetime.datetime(1970, 1, 1)
        dt = datetime.datetime.strptime(time_str, "%Y-%m-%d")
        return int((dt - epoch).total_seconds())
    
    def unix_to_str(self, unix_time):
        return time.strftime("%Y-%m-%d", time.localtime(unix_time))
    
    def call_price(self, ticker_symbol):
        url = self.base_path + f"/v3/quote-short/{ticker_symbol}?apikey={self.api_key}"
        price = self.make_request(url)[0]["price"]
        return ticker_symbol, price
    
    def call_timeseries(self, *args):
        # valid intervals are: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day
        # if interval is 1day dataType must be "close"
        # valid data_types are: open, low, high, close, volume
        # starting_time must be a string of a date or a unix time at which the timeseries should begin
        # returns a timeseries from starting_time to last available data point
        ticker_symbol = args[0]
        kwargs = args[1]
        interval = kwargs["interval"]
        starting_time = kwargs["starting_time"]
        data_type = kwargs["data_type"]
        
        
        stop_at = starting_time # this serves no purpose but increases readability
        if type(stop_at) in [int, float]:
            stop_at = self.unix_to_string(stop_at)
        
        if interval == "1day":
            url = self.base_path + f"/v3/historical-price-full/{ticker_symbol}?serietype=line&apikey={self.api_key}"
            response = self.make_request(url)
        else:  
        
            url = self.base_path + f"/v3/historical-chart/{interval}/{ticker_symbol}?apikey={self.api_key}"
            response = self.make_request(url)

        if interval == "1day":
            response = response["historical"]


        timeseries = []
        stoped_at = response[-1]["date"] # base case
        for data_point in response:
            if data_point["date"] > stop_at:
                timeseries.append(data_point[data_type])
            else:
                
                stoped_at = data_point["date"]
                break

        timeseries.reverse()
        meta_dict = {"ticker_symbol": ticker_symbol, "start": response[0]["date"], "stop": stoped_at}
        timeseries_dict = {"values": timeseries, "meta": meta_dict}
        
        return ticker_symbol, timeseries_dict
        
    def call_stock_data(self, ticker_symbol):
        
        stock_data = {"tickerSymbol": ticker_symbol}        

        url = self.base_path + f'/v3/balance-sheet-statement/{ticker_symbol}?limit=100&apikey={self.api_key}'
        balance_sheets = self.make_request(url)
        
        stock_data["currency"] = balance_sheets[0]["reportedCurrency"]
    
        for balance_sheet in balance_sheets:
            filling_date = self.str_to_unix(balance_sheet["fillingDate"])
            if filling_date not in stock_data:
                stock_data[filling_date] = {}

            stock_data[filling_date]["totalAssets"] = balance_sheet["totalAssets"]
            stock_data[filling_date]["totalLiabilities"] = balance_sheet["totalLiabilities"]
            stock_data[filling_date]["shareholdersEquity"] = balance_sheet["totalStockholdersEquity"]
            stock_data[filling_date]["createdAt"] = round(time.time())
            
            if stock_data["currency"] != balance_sheet["reportedCurrency"]:
                raise InvalidResponse(f'API answer used different currencies <{stock_data["currency"]}> and <{balance_sheet["reportedCurrency"]}>')
            
        url = self.base_path + f'/v3/income-statement/{ticker_symbol}?limit=100&apikey={self.api_key}'
        income_statements = self.make_request(url)
        
        
        for income_statement in income_statements:
            filling_date = self.str_to_unix(income_statement["fillingDate"])
            if filling_date not in stock_data:
                stock_data[filling_date] = {}
            
            if stock_data["currency"] != income_statement["reportedCurrency"]:
                raise InvalidResponse(f'API answer used different currencies <{stock_data["currency"]}> and <{income_statement["reportedCurrency"]}>')
            
            stock_data[filling_date]["ebitda"] = income_statement["ebitda"]
            stock_data[filling_date]["grossProfit"] = income_statement["grossProfit"]
            stock_data[filling_date]["netIncome"] = income_statement["netIncome"]
            stock_data[filling_date]["operatingIncome"] = income_statement["operatingIncome"]
            stock_data[filling_date]["operatingExpenses"] = income_statement["operatingExpenses"]
            stock_data[filling_date]["revenue"] = income_statement["revenue"]
            stock_data[filling_date]["weightedAverageShsOutDil"] = income_statement["weightedAverageShsOutDil"]
            stock_data[filling_date]["operatingIncome"] = income_statement["operatingIncome"]
            stock_data[filling_date]["createdAt"] = round(time.time())
        

        url = self.base_path + f'/v3/profile/{ticker_symbol}?limit=100&apikey={self.api_key}'
        summary = self.make_request(url)[0]

        if stock_data["currency"] != summary["currency"]:
            raise InvalidResponse(f'API answer used different currencies <{stock_data["currency"]}> and <{summary["reportedCurrency"]}>')
        
        stock_data["country"] = summary["country"]
        stock_data["longBusinessSummary"] = summary["description"]
        stock_data["exchangeShortName"] = summary["exchangeShortName"]
        stock_data["fullTimeEmployees"] = summary["fullTimeEmployees"]
        stock_data["image"] = summary["image"]
        stock_data["industry"] = summary["industry"]
        stock_data["companyName"] = summary["companyName"]
        
        stock_data["totalShares"] = round(summary["mktCap"]/summary["price"])

        return ticker_symbol, stock_data
    
    def check_exists(self, ticker_symbol):
        try:
            self.call_price(ticker_symbol)
            return ticker_symbol, True
        except InvalidResponse:
            return ticker_symbol, False

    def get_shares_info(self, *args):
        # share_type can be freeFloat, floatShares, outstandingShares
        ticker_symbol = args[0]
        share_type = args[1]["share_type"]
        
        url = self.base_path + f"/v4/shares_float?symbol={ticker_symbol}&apikey={self.api_key}"
        response = self.make_request(url)
        value = response[0][share_type]
        
        if share_type == "freeFloat":
            return ticker_symbol, value
        else:
            return ticker_symbol, int(value)
    
    
    
    ######################################### finish this when the response is there
    def get_earnings_dates(self, ticker_symbol="all", sort_by="company"):
        # ticker_symbol can be the ticker symbol of a company to recieve the next earning
        # date if applicable or "all" to recieve dates for all companies
        # sort by can be "company" or "date"
        url = self.base_path + f"/v3/earning_calendar?apikey={self.api_key}"
        response = self.make_request(url)
        
        def sort_to_dict(response):
            earnings_by_company = {}
            for raw_dict in response:
                ticker_symbol = raw_dict["symbol"]
                if ticker_symbol not in earnings_by_company:
                     earnings_by_company[ticker_symbol] = []
                earnings_by_company[ticker_symbol].append(raw_dict["date"])
            return earnings_by_company


        if ticker_symbol == "all" and sort_by == "company":
            return sort_to_dict(response)
            
        return response
    
    def get_upcoming_ipo_dates(self):
        
        start_date = self.unix_to_str(time.time())
        end_date = self.unix_to_str(time.time() + 7776000) # + 3 Months
        url = self.base_path + f"/v3/ipo_calendar?from={start_date}&to={end_date}&apikey={self.api_key}"

        response = self.make_request(url)
        
        ipo_dates = {}
        for raw_dict in response:
            ticker_symbol = raw_dict["symbol"]
            if ticker_symbol in raw_dict:
                raise InvalidResponse(f"Company <{ticker_symbol}> has several IPO´s scheduled.")
            ipo_dates[ticker_symbol] = raw_dict["date"]
        return ipo_dates
        
    def get_gainers_losers(self, *args):
        # mode can be "gainers", "loosers" or "both"
        # minimum_change is the minimum absolute change a stock should have to be returned
        minimum_change = args[0]["minimum_change"]
        mode = args[0]["mode"]
        
        url = self.base_path + "/v3/gainers?apikey=" + self.api_key
        gainers = self.make_request(url)
        url = self.base_path + "/v3/losers?apikey=" + self.api_key
        losers = self.make_request(url)

        gainers_losers = {}
        for response in [gainers, losers]:
            for raw_dict in response:
                ticker_symbol = raw_dict["ticker"]
                if ticker_symbol in raw_dict:
                    raise InvalidResponse(f"Company <{ticker_symbol}> is listed several times in Gainers / Loosers API response.")
                
                raw_change = raw_dict["changesPercentage"]
                if "%" in raw_change:
                    raw_change = raw_change.replace("%", "")
                change = float(raw_change) / 100
                if abs(change) >= minimum_change:
                    if mode == "gainers" and change<0:
                        continue
                    if mode == "loosers" and change>0:
                        continue
                    gainers_losers[ticker_symbol] = change
        return gainers_losers
    
    def get_sentiment(self, ticker_symbol):
        # relativeIndex : RHI is a measure of whether people are talking about a stock more or less than usual.
        # generalPerception : SGP is a measure of whether people are more or less positive about a stock than usual.
        # sentiment : Sentiment is the percentage of people that are positive about a stock.
        url = self.base_path + f"/v4/social-sentiment?symbol={ticker_symbol}&limit=100&apikey={self.api_key}"
        response = self.make_request(url)

        sentiment = {}
        sentiment["relativeActivity"] = response[0]["relativeIndex"]
        sentiment["relativeBullish"] = response[0]["generalPerception"]
        sentiment["percentBullish"] = response[0]["sentiment"]
        return ticker_symbol, sentiment
    
    def get_treasury_rates(self, *args):
        days_back = args[0]["days_back"]
        # will return 42 days back at maximum / maybe this will change in the future
        today = self.unix_to_str(time.time())
        back = self.unix_to_str(time.time() - 86400*days_back)
        url = self.base_path + f"/v4/treasury?from={back}&to={today}&apikey={self.api_key}"
        response = self.make_request(url)
        timeseries = {}
        for key in response[0].keys():
            timeseries[key] = []
            for r in response:
                timeseries[key].append(r[key])
            timeseries[key].reverse()
        return timeseries
        
    """
    def get_holders(self, ticker_symbol):
        holdings = {}
        url = self.base_path + f"/v3/profile/{ticker_symbol}?apikey={self.api_key}"
        profile = self.make_request(url)
        total_shares = int(profile[0]["mktCap"] / profile[0]["price"])

        url = self.base_path + f"/v3/institutional-holder/{ticker_symbol}?apikey={self.api_key}"
        institutional = self.make_request(url)
        institutional_holdings = 0
        for raw_dict in institutional:
            institutional_holdings += raw_dict["shares"]
        
        url = self.base_path + f"/v3/mutual-fund-holder/{ticker_symbol}?apikey={self.api_key}"
        fund = self.make_request(url)
        fund_holdings = 0
        for raw_dict in fund:
            fund_holdings += raw_dict["shares"]
        
        
        holdings["totalShares"] = total_shares
        holdings["instituationalHoldings"] = institutional_holdings
        holdings["instituationalHoldingsPercentage"] = institutional_holdings / total_shares
        holdings["mutualFundlHoldings"] = fund_holdings
        holdings["mutualFundlHoldingsPercentage"] = fund_holdings / total_shares
        
        return holdings
    """
    
ticker_symbols = ['DFEN', 'XMA.TO', 'DSSL.NS', 'THS.L', 'KOHINOOR.NS', 'EFF.DE',
               'EMAMILTD.NS', '83118.HK', 'PBUS', 'KWAC-UN', 'STLN.SW', 'SRE.L',
               '0864.HK', 'LCTX', 'JHME', '0713.HK', 'MYFW', 'FSFG', 'EXF.TO',
               'EBMT', 'LABS.TO', 'KRT', '639.DE', 'XEL', 'DFND', 'SDVY',
               '0493.HK', 'LHX', 'DFFN', '1122.HK', 'SMMOX', 'NATI', 'CR',
               '0K7X.L', 'BNC.TO', 'GULPOLY.NS', 'TPB', 'BLCN', '1194.HK',
               'BRZ.L', '3085.HK', 'FKWL', 'SIIDX', 'CTKB', 'MOS.L', 'TOUR',
               'COUNCODOS.NS', 'RWT', '8426.HK', 'ELEV', 'PSX', 'ARQT',
               'KANSAINER.NS', 'HAN.L', 'FHH.TO', '0KW1.L', '0460.HK', 'XDU.TO',
               '8210.HK', 'INS.DE', 'RYCVX', '0Z62.L', '2682.HK', 'TUGC', 'SCDL',
               'INOC.TO', '0128.HK', 'KMB', 'GRF', '0248.HK', 'TVE', 'ESP',
               'QLVE', 'BNB.BR', 'MDGL', 'FDC.NS', 'AQSP', 'FHN-PE', 'HEZU',
               'CAH', 'DUKE.L', '0102.HK', 'HILRX', 'TDTT', 'TEAF', 'GBLX',
               'MMIT.L', 'SGEN', 'GOLD.TO', '0I4Q.L', '0101.HK', 'B8A.DE',
               'DLG.DE', 'NNSB.ME', 'VSTIND.NS', 'KOR', 'NONG.OL', 'DTOCU',
               'SKYT']

class RateLimiter: # nice idea but probably not needed
    def __init__(self, interval):
        self.interval = interval
        self.next_call = 0

    def __next__(self):
        t = time.monotonic()
        if t < self.next_call:
            time.sleep(self.next_yield - t)
            t = time.monotonic()
        self.next_call = t + self.interval

class MultiThreader:
    def __init__(self, api):
        self.api = api
        self.limit_per_second = self.api.limit_per_second
        self.executor = ThreadPoolExecutor(max_workers=self.limit_per_second)
    
    def make_request(self, *args, **kwargs):
        # *args: function, list of ticker symbols
        # **kwargs: kwargs to pass to the function
        function = args[0]
        ticker_symbols = False
        if len(args) == 2:
            ticker_symbols = args[1] 
        response, threads = {}, []
        if kwargs and ticker_symbols:
            for ticker_symbol in ticker_symbols:
                threads.append(self.executor.submit(function, ticker_symbol, kwargs))
        elif ticker_symbols:
            for ticker_symbol in ticker_symbols:
                threads.append(self.executor.submit(function, ticker_symbol))
        elif kwargs:
            return function(kwargs)
        else:
            return function()
        
        for task in as_completed(threads):
            try:
                result = task.result()
                response[result[0]] = result[1]
            except:
                print("Error occured:", task.exception(), "excluding result from answer.")
        return response
    
    def call_price(self, ticker_symbols):
        return self.make_request(self.api.call_price, ticker_symbols)
    
    def call_timeseries(self, ticker_symbols, interval, starting_time, data_type="close"):
        return self.make_request(self.api.call_timeseries, ticker_symbols, interval=interval, starting_time=starting_time, data_type=data_type)
    
    def call_stock_data(self, ticker_symbols):
        try:
            self.executor = ThreadPoolExecutor(max_workers=int(self.limit_per_second*0.7))
            result = self.make_request(self.api.call_stock_data, ticker_symbols)
            self.executor = ThreadPoolExecutor(max_workers=self.limit_per_second)
        except Exception as e:
            self.executor = ThreadPoolExecutor(max_workers=int(self.limit_per_second))
            print("Unclassfified Error during API call:", e)
            return

        return result
    
    def check_exists(self, ticker_symbols):
        return self.make_request(self.api.check_exists, ticker_symbols)
    
    def get_shares_info(self, ticker_symbols, share_type="outstandingShares"):
        return self.make_request(self.api.get_shares_info, ticker_symbols, share_type=share_type)
    
    def get_upcoming_ipo_dates(self):
        return self.api.single.get_upcoming_ipo_dates()
    
    def get_gainers_losers(self, minimum_change=0.1, mode="both"):
        return self.make_request(self.api.get_gainers_losers, minimum_change=minimum_change, mode=mode)
    
    def get_sentiment(self, ticker_symbols):
        return self.make_request(self.api.get_sentiment, ticker_symbols)
    
    def get_treasury_rates(self, days_back):
        return self.api.single.get_treasury_rates(days_back)
    
    def get_all_company_tickers(self):
        return self.api.single.get_all_company_tickers()

