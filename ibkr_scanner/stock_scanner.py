from ib_async import * 
import argparse

#HOST = '127.0.0.1'
#PORT = 7496 #TWS 4001 #GATEWAY 
#CLIENT_ID = 12

#util.startLoop() # Starts loop that allows us to work with the API in Jupyter notebooks – this is not necessary in a script
ib = IB() # Creates an instance of the IB client class
#ib.connect(HOST, PORT, CLIENT_ID) # Connects to TWS


def print_scan_item(item):
    cd = item.contractDetails
    c = cd.contract
    primary_exch = (
        getattr(c, "primaryExchange", "")
        or (cd.validExchanges.split(",")[0] if getattr(cd, "validExchanges", "") else "")
        or getattr(cd, "marketName", "")
    )
    # Display price if available
    price_str = f"${item.marketDataSnapshot.last:.2f}" if hasattr(item, 'marketDataSnapshot') and item.marketDataSnapshot and item.marketDataSnapshot.last else "N/A"
    print(f"[{item.rank:>3}] {c.symbol:<8} {c.secType:<3} {primary_exch:<10} {price_str:>8}")


def main():
    parser = argparse.ArgumentParser(description="IBKR TWS stock scanner using ib_async")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7496, help="7497 paper, 7496 live")
    parser.add_argument("--client-id", type=int, default=1)
    parser.add_argument("--instrument", default="STK")
    parser.add_argument("--location-code", default="STK.US.MAJOR")
    parser.add_argument("--scan-code", default="TOP_PERC_GAIN",
                        help="Examples: TOP_PERC_GAIN, TOP_PERC_LOSE, MOST_ACTIVE, HOT_BY_VOLUME, TOP_OPEN_PERC_GAIN")
    parser.add_argument("--stream-seconds", type=int, default=0,
                        help="If > 0, stream updates for this many seconds; else snapshot")
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Minimum stock price to include (excludes penny stocks)")
    parser.add_argument("--max-price", type=float, default=None,
                        help="Maximum stock price to include (optional)")
    args = parser.parse_args()


    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id)

    # Create scanner subscription with price filters
    sub = ScannerSubscription(
        instrument=args.instrument,
        locationCode=args.location_code,
        scanCode=args.scan_code
    )
    
    # Add price filters to exclude penny stocks
    if args.min_price is not None:
        sub.abovePrice = args.min_price
    if args.max_price is not None:
        sub.belowPrice = args.max_price

    if args.stream_seconds > 0:
        scan_data_list = ib.reqScannerData(sub)

        def on_update(items):
            for item in items:
                print_scan_item(item)

        scan_data_list.updateEvent += on_update
        ib.sleep(args.stream_seconds)
        ib.cancelScannerSubscription(scan_data_list)
    else:
        items = ib.reqScannerData(sub)
        for item in items:
            print_scan_item(item)

    ib.disconnect()

if __name__ == "__main__":
    main()

'''
#contract = Forex('EURUSD')
stock = Stock('BABA','SMART','USD')

bars = ib.reqHistoricalData(
    stock, endDateTime='', durationStr='30 D',
    barSizeSetting='1 hour', whatToShow='MIDPOINT', useRTH=True)

#convert to pandas df:
df = util.df(bars) 
print(df)
'''