# total shares is actually shares outstanding
# Documentation is at: https://financialmodelingprep.com/developer/docs/
# Date format is always: "YYYY-MM-DD" e.g. "2021-11-08"

import hashlib
from bs4 import BeautifulSoup
import urllib
import time
import urllib.request
import requests
import datetime
import warnings
import numpy as np
from sklearn.linear_model import LinearRegression
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib.pyplot as plt
import json
import numpy as np
from auxiliary_functions import is_number


class InvalidResponse(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
        
class InvalidRequest(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class FinancialModelingPrep:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_path = "https://financialmodelingprep.com/api"
    
    def make_request(self, url):
        response = requests.request("GET", url).json()
        if response == []:
            raise InvalidResponse(f"Invalid Response from API for url <{url}>")
        elif "Error Message" in response:
            raise InvalidResponse(f'{response["Error Message"]}. url: {url}')
        
        return response
    
    def str_to_unix(self, time_str):
        time_str = time_str[:10]
        epoch = datetime.datetime(1970, 1, 1)
        dt = datetime.datetime.strptime(time_str, "%Y-%m-%d")
        return int((dt - epoch).total_seconds())
    
    def unix_to_str(self, unix_time):
        return time.strftime("%Y-%m-%d", time.localtime(unix_time))
    
    def call_timeseries(self, ticker_symbol, interval, starting_time, data_type, reloading=False):
        # valid intervals are: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day
        # if interval is 1day dataType must be "close"
        # valid data_types are: open, low, high, close, volume
        # starting_time must be a string of a date or a unix time at which the timeseries should begin
        # returns a timeseries from starting_time to last available data point
        
        stop_at = starting_time # this serves no purpose but increases readability
        if type(stop_at) in [int, float]:
            stop_at = self.unix_to_str(stop_at)
        
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
        
        return timeseries_dict
        
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

        return stock_data
    
    def get_price(self, ticker_symbol, currency=None):
        url = self.base_path + f"/v3/quote-short/{ticker_symbol}?apikey={self.api_key}"
        price = self.make_request(url)[0]["price"]
        if currency is None:
            return price
        else:
            report_currency = self.get_currency(ticker_symbol)
            if report_currency == currency:
                return price
            else:
                return self.convert_currency(report_currency, currency, price)

    def get_past_price(self, ticker_symbol, unix_time):
        seconds_back = time.time() - unix_time
        interval = "1day"
        if seconds_back <= 60*60*24*60:
            interval = "30min"
        if seconds_back <= 60*60*24*20:
            interval = "15min"
        if seconds_back <= 60*60*24*5:
            interval = "5min"
        if seconds_back <= 60*60*24:
            interval = "1min"

        series = self.call_timeseries(ticker_symbol, interval, unix_time, "close")
        if self.str_to_unix(series["meta"]["stop"]) - unix_time >= 60*60*24*5:
            raise RuntimeError(f'Difference between requested Date <{self.unix_to_str(unix_time)}> and returned Date <{series["meta"]["stop"]}> is too big.')
        return series["values"][0]

    def check_exists(self, ticker_symbol):
        try:
            self.get_price(ticker_symbol)
            return True
        except InvalidResponse:
            return False

    def get_shares_info(self, ticker_symbol, share_type="outstandingShares"):
        # share_type can be freeFloat, floatShares, outstandingShares
        url = self.base_path + f"/v4/shares_float?symbol={ticker_symbol}&apikey={self.api_key}"
        response = self.make_request(url)
        value = response[0][share_type]
        
        if share_type == "freeFloat":
            return value
        else:
            return int(value)
    
    
    
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
        
    def get_gainers_losers(self, minimum_change=0.1, mode="both"):
        # mode can be "gainers", "loosers" or "both"
        # minimum_change is the minimum absolute change a stock should have to be returned
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
        return sentiment
    
    def get_treasury_rates(self, days_back):
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
        
    def get_all_company_tickers(self):
        url = self.base_path + "/v3/financial-statement-symbol-lists?apikey=" + self.api_key
        response = self.make_request(url)
        response.remove("Cash")
        return response

    def get_index_timeseries(self, ticker_symbol, date):
        # date: must be in format YYYYMMDD
        def increment(time):
            hour = int(time[:2])
            minute = int(time[3:])
            if minute == 59:
                hour += 1
                minute = 0
            else:
                minute += 1
            minute, hour = str(minute), str(hour)
            if len(minute) == 1:
                minute = "0" + minute
            if len(hour) == 1:
                hour = "0" + hour
            return hour + ":" + minute
        
        date = date[:4] + "-" + date[4:6] + "-" + date[6:]
        url = f"/api/v4/historical-price-index/{ticker_symbol}/1/minute/{date}/{increment(date, 1)}?apikey={self.api_key}"
        result = self.make_request(url)
        result.reverse()
        
        vars_to_save = ["close", "low", "high", "volume"]
        timeseries = {}
        for var in vars_to_save:
            timeseries[var] = []
        last_time = "09:29"
        missing = 0
        for point in result:
            if point["date"][:10] != date:
                continue
            current_time = point["date"][11:16]
            if current_time != increment(last_time):
                missing += 1
                print(f"Missing value for <{ticker_symbol}>, <{date}>, <{current_time}>")
                for var in vars_to_save:
                    timeseries[var].append(None)
            for var in vars_to_save:
                timeseries[var].append(point[var])
            last_time = current_time
        length = len(timeseries["close"])
        if not length:
            raise InvalidResponse(f"Date <{date}> is not available for <{ticker_symbol}>")
        if length != 391:
            raise InvalidResponse(f"Timeseries is not complete for <{ticker_symbol}> for date: <{date}> length is <{length}>")
        if missing >= 5:
            warnings.warn(f"Number of missing values in timeseries is <{missing}>")
        return timeseries

    def get_ratios(self, ticker_symbol):
        url = f"{self.base_path}/v3/ratios-ttm/{ticker_symbol}?apikey={self.api_key}"
        response = self.make_request(url)[0]
        values = list(response.values())
        if values.count(None) == len(values):
            raise InvalidResponse(f"API returned None for all values")
        return response

    def get_analyst_estimates(self, ticker_symbol):
        url = f"{self.base_path}/v3/analyst-estimates/{ticker_symbol}?period=quarter&limit=30&apikey={self.api_key}"
        return self.make_request(url)

    def get_analyst_estimates_processed(self, ticker_symbol, n_periods=4, direction="forewards"):
        # direction must be "forewards" or "backwards"
        response = self.get_analyst_estimates(ticker_symbol)
        if direction == "forewards":
            response.reverse()
        estimates = {}
        for point in response:
            if len(estimates) == n_periods:
                break
            if direction == "forewards" and self.str_to_unix(point["date"]) >= time.time():
                estimates[point["date"]] = point
            elif direction == "backwards" and self.str_to_unix(point["date"]) <= time.time():
                estimates[point["date"]] = point

        if len(estimates) == n_periods:
            return estimates
        else:
            raise InvalidResponse("Analyst Estimates not available for specified settings.")

    def get_ranking(self, ticker_symbol):
        url = f"{self.base_path}/v3/rating/{ticker_symbol}?apikey={self.api_key}"
        return self.make_request(url)[0]

    def get_currency(self, ticker_symbol):
        url = f"{self.base_path}/v3/profile/{ticker_symbol}?apikey={self.api_key}"
        return self.make_request(url)[0]["currency"]

    def convert_currency(self, convert_from, convert_to, value):
        # value can be a single value or an iterator of values
        if convert_from == convert_to:
            return value
        url = f"{self.base_path}/v3/historical-chart/1min/{convert_from}{convert_to}?apikey={self.api_key}"
        rate = self.make_request(url)[0]["close"]
        if is_number(value):
            return rate * value
        else:
            response = []
            for val in value:
                response.append(val * rate)
            return response
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

class ReverseEngineered:
    def __init__(self, fmp_key):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.fmp = FinancialModelingPrep(fmp_key)

    def make_request(self, url):
        response = requests.get(url).json()
        if len(response) != 1:
            raise RuntimeError(f"Unexpected response format: {response}")
        response = next(iter(response.values()))
        if "error" in response:
            raise InvalidResponse(response["reason"])
        return response

    def get_rank(self, ticker_symbol, internal=False):
        url = r"https://quote-feed.zacks.com/index?t=" + ticker_symbol

        response = requests.get(url).json()
        if len(response) != 1:
            raise RuntimeError(f"Unexpected response format: {response}")
        response = next(iter(response.values()))
        if "error" in response:
            raise InvalidResponse(response["reason"])

        rank = response["zacks_rank"]
        if rank not in ["1", "2", "3", "4", "5"]:
            raise InvalidResponse(f"Invalid rank returned <{rank}>")

        if internal:
            return ticker_symbol, int(rank)
        else:
            return int(rank)

    def get_ranks(self, ticker_symbols):
        response, threads = {}, []
        for ticker_symbol in ticker_symbols:
            threads.append(self.executor.submit(self.get_rank, ticker_symbol, True))

        for task in as_completed(threads):
            try:
                result = task.result()
                response[result[0]] = result[1]
            except:
                print(f"Error occured: {task.exception()}. excluding result from answer.")
        return response

    def get_price_target(self, ticker_symbol, desired_currency="USD", internal=False):
        url = f"https://tr-frontend-cdn.azureedge.net/bff/prod/stock/{ticker_symbol.lower()}/payload.json"
        try:
            response = requests.get(url).json()
        except json.decoder.JSONDecodeError:
            raise InvalidResponse(f"Could not decode response, the ticker symbol <{ticker_symbol}> is probably unavailable")


        currency = response["common"]["stock"]["currency"]
        price_target = response["common"]["stock"]["analystRatings"]["bestConsensus"]["priceTarget"]["value"]
        if currency != desired_currency:
            price_target = self.fmp.convert_currency(currency, desired_currency, price_target)

        if internal:
            return ticker_symbol, price_target
        else:
            return price_target

    def get_price_targets(self, ticker_symbols, desired_currency="USD"):
        response, threads = {}, []
        for ticker_symbol in ticker_symbols:
            threads.append(self.executor.submit(self.get_price_target, ticker_symbol, desired_currency, True))

        for task in as_completed(threads):
            try:
                result = task.result()
                response[result[0]] = result[1]
            except:
                print(f"Error occured: {task.exception()}. excluding result from answer.")
        return response

    def get_upwards_potential(self, ticker_symbol, internal=False):
        price_target = self.get_price_target(ticker_symbol)
        price = self.fmp.get_price(ticker_symbol)
        if price_target is None:
            raise InvalidResponse("Price target cannot be found.")
        elif internal:
            return ticker_symbol, (price_target - price) / price
        else:
            return (price_target - price) / price

    def get_upward_potentials(self, ticker_symbols):
        response, threads = {}, []
        for ticker_symbol in ticker_symbols:
            threads.append(self.executor.submit(self.get_upwards_potential, ticker_symbol, True))

        for task in as_completed(threads):
            try:
                result = task.result()
                response[result[0]] = result[1]
            except:
                print(f"Error occurred: {task.exception()}. excluding result from answer.")
        return response

class APIS:
    def __init__(self, apis):
        self.apis = apis

    def call(self, fn, *args, **kwargs):
        not_have_function = []
        invalid_requests = []
        invalid_responses = []
        for api in self.apis:
            try:
                return getattr(api, fn)(*args, **kwargs)
            except AttributeError:
                not_have_function.append(api)
            except InvalidResponse:
                invalid_responses.append(api)
            except InvalidRequest:
                invalid_requests.append(api)
        raise InvalidRequest(f"No valid response, not_have_function: {not_have_function}, invalid_requests: {invalid_requests}, invalid_responses: {invalid_responses}")

