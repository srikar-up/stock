"""
Unit & Integration Verification Tests for Structural Intelligence Layer
Verifies strict adherence to schemas and behavioral directives.
"""
from matcher import TickerMatcher
from storage import FirestoreContextManager
from agent import NeedleStockAgent


def test_directives():
    print("=" * 60)
    print("🧪 VERIFYING BEHAVIORAL DIRECTIVES & SCHEMAS")
    print("=" * 60)

    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)
    user = "analyst@hedgefund.com"

    # DIRECTIVE 1: GREETING & INTRO ROUTING
    # "hi", "hello" must instantly route to chat without guessing tickers
    res_hi = agent.route_intent("Hello there!", user_context={})
    print(f"\n[Test 1] Query: 'Hello there!' -> Action: {res_hi.get('action')}")
    assert res_hi.get("action") == "chat", f"Expected 'chat', got {res_hi.get('action')}"

    res_hey = agent.route_intent("hi", user_context={})
    assert res_hey.get("action") == "chat"

    # DIRECTIVE 3: BOUNDARY CHECK (COMPARE MAX 2)
    # 3+ stocks must drop to chat
    res_overload = agent.route_intent("Compare Apple, Microsoft, Tesla", user_context={})
    print(f"\n[Test 2] Overload Query (3 stocks) -> Action: {res_overload.get('action')}")
    assert res_overload.get("action") == "chat", f"Expected 'chat' for 3 stocks, got {res_overload.get('action')}"

    # Valid 2-stock comparison
    res_compare = agent.route_intent("Compare Apple and Microsoft", user_context={})
    print(f"\n[Test 3] Compare 2 stocks -> Action: {res_compare.get('action')}, Symbols: {res_compare.get('parameters', {}).get('symbols')}")
    assert res_compare.get("action") == "compare_stocks"
    assert res_compare.get("parameters", {}).get("symbols") == ["AAPL", "MSFT"]

    # SCHEMA: get_stock_info
    res_quote = agent.route_intent("What is Tesla's current price?", user_context={})
    print(f"\n[Test 4] Query: 'What is Tesla's current price?' -> Action: {res_quote.get('action')}, Symbol: {res_quote.get('parameters', {}).get('symbol')}")
    assert res_quote.get("action") == "get_stock_info"
    assert res_quote.get("parameters", {}).get("symbol") == "TSLA"

    # Save TSLA to context
    ctx_mgr.update_user_context(user, last_ticker="TSLA", last_action="get_stock_info")
    saved_ctx = ctx_mgr.get_user_context(user)

    # DIRECTIVE 2: METADATA CONTEXT MEMORY (Pronoun substitution)
    # "show me its chart" should substitute "its" with TSLA from context
    res_context = agent.route_intent("Show me its chart for 1 year", user_context=saved_ctx)
    print(f"\n[Test 5] Context Query: 'Show me its chart for 1 year' -> Action: {res_context.get('action')}, Symbol: {res_context.get('parameters', {}).get('symbol')}, Period: {res_context.get('parameters', {}).get('period')}")
    assert res_context.get("action") == "show_chart"
    assert res_context.get("parameters", {}).get("symbol") == "TSLA"
    assert res_context.get("parameters", {}).get("period") == "1y"

    # SCHEMA: get_csv
    res_csv = agent.route_intent("Send me csv data for that stock", user_context=saved_ctx)
    print(f"\n[Test 6] CSV Query: 'Send me csv data for that stock' -> Action: {res_csv.get('action')}, Symbol: {res_csv.get('parameters', {}).get('symbol')}")
    assert res_csv.get("action") == "get_csv"
    assert res_csv.get("parameters", {}).get("symbol") == "TSLA"

    # DIRECTIVE 4: MULTI-TICKER CONTEXT MEMORY ("both")
    ctx_mgr.update_user_context(user, last_ticker="AAPL", last_tickers=["AAPL", "MSFT"], last_action="compare_stocks")
    saved_multi_ctx = ctx_mgr.get_user_context(user)

    res_both_csv = agent.route_intent("Show CSV data for both", user_context=saved_multi_ctx)
    print(f"\n[Test 7] Follow-up Query: 'Show CSV data for both' -> Action: {res_both_csv.get('action')}, Symbols: {res_both_csv.get('parameters', {}).get('symbols')}")
    assert res_both_csv.get("action") == "get_comparative_csv"
    assert res_both_csv.get("parameters", {}).get("symbols") == ["AAPL", "MSFT"]

    res_both_chart = agent.route_intent("Show chart for both", user_context=saved_multi_ctx)
    print(f"\n[Test 8] Follow-up Query: 'Show chart for both' -> Action: {res_both_chart.get('action')}, Symbols: {res_both_chart.get('parameters', {}).get('symbols')}")
    assert res_both_chart.get("action") == "compare_stocks"
    assert res_both_chart.get("parameters", {}).get("symbols") == ["AAPL", "MSFT"]

    print("\n" + "=" * 60)
    print("✅ ALL BEHAVIORAL DIRECTIVES & SCHEMAS VERIFIED SUCCESSFULLY!")
    print("=" * 60)


def test_process_message_pipeline():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING FULL PROCESS_MESSAGE PIPELINE (NEEDLE / FALLBACK)")
    print("=" * 60)

    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)
    user = "trader@fund.com"

    res = agent.process_message(user, subject="Apple Inquiry", body="What is Apple price?")
    print(f"Engine used: {res.get('engine')}, Intent: {res.get('intent')}, Ticker: {res.get('ticker')}")
    assert res.get("intent") == "QUOTE"
    assert res.get("ticker") == "AAPL"
    print("✅ Full execution pipeline verified!")


def test_time_extraction():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING TIME PERIOD EXTRACTION (MONTHLY, 6-MONTH, TYPOS)")
    print("=" * 60)

    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)

    # 1. 6 month and typos ("6 nont", "6 mont", "6m")
    assert agent.extract_period("show 6 month chart for tsla") == "6mo"
    assert agent.extract_period("show 6 nont chart for tsla") == "6mo"
    assert agent.extract_period("show 6 mont chart for tsla") == "6mo"
    assert agent.extract_period("show 6m chart for tsla") == "6mo"
    assert agent.extract_period("6 months trend of apple") == "6mo"

    # 2. Monthly and typos ("montly", "1mo", "1 month")
    assert agent.extract_period("show monthly chart for nvda") == "1mo"
    assert agent.extract_period("show montly chart for nvda") == "1mo"
    assert agent.extract_period("show 1mo chart for nvda") == "1mo"
    assert agent.extract_period("show 1 month chart for nvda") == "1mo"

    # 3. 1 year, 2 year, 5 year
    assert agent.extract_period("show 1 year chart for nvda") == "1y"
    assert agent.extract_period("show 1y chart for nvda") == "1y"
    assert agent.extract_period("show 5 year chart for nvda") == "5y"

    # 4. Routing with period
    res = agent.route_intent("show 6 nont chart for nvda", user_context={})
    assert res.get("action") == "show_chart"
    assert res.get("parameters", {}).get("period") == "6mo"
    assert res.get("parameters", {}).get("symbol") == "NVDA"

    res_monthly = agent.route_intent("montly chart for apple", user_context={})
    assert res_monthly.get("action") == "show_chart"
    assert res_monthly.get("parameters", {}).get("period") == "1mo"
    assert res_monthly.get("parameters", {}).get("symbol") == "AAPL"

    print("✅ All time period extractions (monthly, 6mo, 1y, typos) verified successfully!")


def test_thread_suggestions():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING SAME-THREAD SUGGESTIONS & NATIVE REPLY CONTINUITY")
    print("=" * 60)

    from main import format_html_email_response
    html = format_html_email_response({
        "intent": "QUOTE",
        "ticker": "AAPL",
        "data": {
            "success": True,
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "current_price": 230.5,
            "change": 1.25,
            "pct_change": 0.54
        }
    }, "user@example.com", reply_subject="Re: My Portfolio")

    # Mailto buttons are intentionally omitted to avoid breaking email threads via compose popups
    assert "<a href=\"mailto:" not in html, "Should not use mailto: links which break email threading"
    assert "Suggested Follow-up Questions" in html, "Expected Suggested Follow-up Questions card"
    assert "Reply" in html, "Expected Reply instruction"

    print("✅ Thread-safe email suggestions verified with exact thread preservation!")


def test_csv_sheets_and_not_found():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING CSV/SHEETS INTENT ROUTING & NOT_FOUND COMPANY HANDLING")
    print("=" * 60)

    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)

    # 1. Sheets & CSV variations
    res_sheet = agent.route_intent("send me the sheet for tatamotors", user_context={})
    assert res_sheet.get("action") == "get_csv", f"Expected 'get_csv', got {res_sheet.get('action')}"
    assert res_sheet.get("parameters", {}).get("symbol") == "TATAMOTORS.NS"

    res_csv = agent.route_intent("upload csv sheets for apple", user_context={})
    assert res_csv.get("action") == "get_csv"
    assert res_csv.get("parameters", {}).get("symbol") == "AAPL"

    res_excel = agent.route_intent("send excel data of microsoft", user_context={})
    assert res_excel.get("action") == "get_csv"
    assert res_excel.get("parameters", {}).get("symbol") == "MSFT"

    # 2. Unknown company handling (NOT_FOUND)
    res_unknown = agent.route_intent("what is the stock price of zeptononexistent?", user_context={})
    assert res_unknown.get("action") == "not_found", f"Expected 'not_found', got {res_unknown.get('action')}"
    assert "not found in our database" in res_unknown.get("message")

    print("✅ CSV/sheets intent and company not found handling verified successfully!")



def test_companies_json_integration():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING COMPANIES.JSON DYNAMIC DATASET INGESTION")
    print("=" * 60)

    matcher = TickerMatcher()
    print(f"Total mapped company aliases: {len(matcher.company_names_map)}")
    assert len(matcher.company_names_map) > 50, "Expected companies.json dataset to expand mapping"

    # Test lookups from companies.json
    assert matcher.extract_ticker_from_text("price of saudi aramco")[0] == "2222.SR"
    assert matcher.extract_ticker_from_text("show 6 month chart for toshiba")[0] == "6502.T"
    assert matcher.extract_ticker_from_text("what is samsung price?")[0] == "005930.KS"
    assert matcher.extract_ticker_from_text("novo nordisk trend")[0] == "NVO"

    # Test Agent routing
    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)

    res = agent.route_intent("show 6 month chart for toshiba", user_context={})
    assert res.get("action") == "show_chart"
    assert res.get("parameters", {}).get("symbol") == "6502.T"
    assert res.get("parameters", {}).get("period") == "6mo"

def test_months_typo_not_confused_with_company_and_mobile_responsive():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING 'MONTS' NEVER CONFUSED WITH 'MNTS' & MOBILE RESPONSIVENESS")
    print("=" * 60)

    matcher = TickerMatcher()
    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)

    # 1. 'chart of microsoft last 6 monts' MUST resolve strictly to MSFT (6mo) and NEVER MNTS
    tickers = [t for t, _ in matcher.extract_all_tickers("chart of microsoft last 6 monts")]
    print(f"Extracted tickers for 'chart of microsoft last 6 monts': {tickers}")
    assert tickers == ["MSFT"], f"Expected ['MSFT'], got {tickers}"
    assert "MNTS" not in tickers, "MNTS must NEVER be extracted from typo '6 monts'!"

    res = agent.route_intent("chart of microsoft last 6 monts", user_context={})
    print(f"Routing result: Action={res.get('action')}, Symbol={res.get('parameters', {}).get('symbol')}, Period={res.get('parameters', {}).get('period')}")
    assert res.get("action") == "show_chart"
    assert res.get("parameters", {}).get("symbol") == "MSFT"
    assert res.get("parameters", {}).get("period") == "6mo"

    # 2. Check mobile-responsive email HTML
    from stock_bot import StockEmailBot
    bot = StockEmailBot()
    html = bot._build_email_body({
        "intent": "CHART",
        "ticker": "MSFT",
        "period": "6mo",
        "quote": {"success": True, "current_price": 493.78, "pct_change": -0.63}
    }, "user@example.com")

    # Mobile overflow defenses
    assert "box-sizing: border-box" in html, "Master HTML must enforce border-box globally"
    assert "word-break: break-word" in html, "Must contain word-break to prevent text overflow"
    assert "@media only screen and (max-width: 600px)" in html, "Must contain responsive mobile media queries"
    assert "Compare MSFT" in html, "Must offer smart comparative follow-up choices"

    print("✅ 'monts' time typo protection and mobile-responsive layout verified successfully!")


def test_context_memory_both_and_period_sanitization():
    print("\n" + "=" * 60)
    print("🧪 VERIFYING 'BOTH' CONTEXT MEMORY & PERIOD SANITIZATION")
    print("=" * 60)

    from market import MarketEngine, sanitize_period

    # 1. sanitize_period tests
    assert sanitize_period("2") == "2y"
    assert sanitize_period("1m") == "1mo"
    assert sanitize_period("6m") == "6mo"
    assert sanitize_period("6monts") == "6mo"
    assert sanitize_period("invalid") == "1mo"
    assert sanitize_period(None) == "1mo"

    # 2. Context memory with "both"
    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)

    # Seed context with 2 tickers
    user = "test_both@example.com"
    ctx_mgr.update_user_context(user, last_ticker="MSFT", last_tickers=["MSFT", "AAPL"], last_action="compare_stocks")

    res = agent.process_message(user, subject="Re: stocks", body="Show CSV data for both")
    print(f"Result for 'Show CSV data for both': Intent={res.get('intent')}, Tickers={res.get('tickers')}, Period={res.get('period')}")
    assert res.get("intent") == "COMPARATIVE_CSV"
    assert res.get("tickers") == ["MSFT", "AAPL"]
    assert "MAX" not in (res.get("tickers") or [])

    # 3. Test "Show me its 6 month chart"
    res_pronoun = agent.process_message(user, subject="Re: stocks", body="Show me its 6 month chart")
    print(f"Result for 'Show me its 6 month chart': Intent={res_pronoun.get('intent')}, Ticker={res_pronoun.get('ticker')}, Period={res_pronoun.get('period')}")
    assert res_pronoun.get("intent") == "CHART"
    assert res_pronoun.get("ticker") == "MSFT"
    assert res_pronoun.get("ticker") != "SHOW"
    assert res_pronoun.get("period") == "6mo"

    # 4. Symbol resolver rejects STOPWORDS
    assert agent._resolve_symbol("SHOW") is None
    assert agent._resolve_symbol("MAX") is None
    assert agent._resolve_symbol("BOTH") is None
    assert agent._resolve_symbol("apple") == "AAPL"

    print("✅ Context memory ('both', 'its'), stopword protection, and period sanitization verified successfully!")


if __name__ == "__main__":
    test_directives()
    test_process_message_pipeline()
    test_time_extraction()
    test_thread_suggestions()
    test_csv_sheets_and_not_found()
    test_companies_json_integration()
    test_months_typo_not_confused_with_company_and_mobile_responsive()
    test_context_memory_both_and_period_sanitization()

