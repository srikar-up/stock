from matcher import TickerMatcher

m = TickerMatcher()

tests = [
    "What is Apple price?",
    "Apple",
    "apple",
    "Can you check apple price for me",
    "Stock query What is Apple price",
    "stonks.gro@gmail.com apple",
    "from: user@gmail.com subject: Apple",
    "Hi, how is apple doing?",
    "Show me apple chart",
    "Can you check the price of Apple",
]

print("\n--- Testing Apple Queries ---")
for t in tests:
    ticker, conf, name, is_fuzzy = m.extract_ticker_from_text(t)
    print(f"'{t}' -> {ticker} ({name}, {conf}%)")
    assert ticker == "AAPL", f"FAILED: Expected AAPL, got {ticker}"

print("\n🎉 All Apple tests passed! AAPL is 100% matched, zero Salesforce hallucination.")
