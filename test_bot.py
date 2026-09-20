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


if __name__ == "__main__":
    test_directives()
    test_process_message_pipeline()
