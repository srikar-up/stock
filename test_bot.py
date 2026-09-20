"""
Unit & Integration Verification Tests for Edge-AI Stock Email Bot
"""
import sys
import os

from matcher import TickerMatcher
from storage import FirestoreContextManager
from agent import NeedleStockAgent
from market import MarketEngine


def test_ticker_matcher():
    print("\n--- 1. Testing TickerMatcher ---")
    matcher = TickerMatcher(confidence_threshold=55.0)

    # Exact matches
    t, conf, name, is_fuzzy = matcher.extract_ticker_from_text("What is Apple stock doing?")
    print(f"Query: 'What is Apple stock doing?' -> Ticker: {t}, Conf: {conf}%, Name: {name}, Fuzzy: {is_fuzzy}")
    assert t == "AAPL", f"Expected AAPL, got {t}"

    # Fuzzy matches with typos
    t, conf, name, is_fuzzy = matcher.extract_ticker_from_text("gool price")
    print(f"Query: 'gool price' -> Ticker: {t}, Conf: {conf}%, Name: {name}, Fuzzy: {is_fuzzy}")
    assert t == "GOOGL", f"Expected GOOGL for 'gool', got {t}"
    assert conf >= 55.0, f"Expected conf >= 55, got {conf}"

    t, conf, name, is_fuzzy = matcher.extract_ticker_from_text("amazn stock today")
    print(f"Query: 'amazn stock today' -> Ticker: {t}, Conf: {conf}%, Name: {name}, Fuzzy: {is_fuzzy}")
    assert t == "AMZN", f"Expected AMZN for 'amazn', got {t}"

    # Ambiguous / Non-stock queries
    t, conf, name, is_fuzzy = matcher.extract_ticker_from_text("hello there friend")
    print(f"Query: 'hello there friend' -> Ticker: {t}")
    assert t is None, f"Expected None for non-stock query, got {t}"

    print("✅ TickerMatcher tests passed!")


def test_context_storage():
    print("\n--- 2. Testing State Persistence ---")
    ctx_mgr = FirestoreContextManager()
    user = "investor@example.com"

    # Set initial context
    updated = ctx_mgr.update_user_context(user, last_ticker="TSLA", last_action="QUOTE")
    assert updated.get("last_ticker") == "TSLA"
    assert updated.get("last_action") == "QUOTE"

    # Read context back
    read_back = ctx_mgr.get_user_context(user)
    assert read_back.get("last_ticker") == "TSLA"
    print(f"Retrieved context for {user}: {read_back}")
    print("✅ State Persistence tests passed!")


def test_agent_intent_and_context_tracking():
    print("\n--- 3. Testing NeedleStockAgent & Sequential Context ---")
    ctx_mgr = FirestoreContextManager()
    agent = NeedleStockAgent(context_manager=ctx_mgr)
    test_user = "trader_alice@hedgefund.com"

    # Step A: User asks for Apple quote
    res1 = agent.process_message(test_user, subject="Apple Inquiry", body="Can you check apple price for me?")
    print(f"Step 1 Intent: {res1.get('intent')}, Ticker: {res1.get('ticker')}")
    assert res1.get("intent") == "QUOTE"
    assert res1.get("ticker") == "AAPL"

    # Verify context saved
    ctx = ctx_mgr.get_user_context(test_user)
    assert ctx.get("last_ticker") == "AAPL"

    # Step B: User asks for chart without mentioning the ticker (context continuation)
    res2 = agent.process_message(test_user, subject="Follow up", body="Please send me the technical chart")
    print(f"Step 2 Intent: {res2.get('intent')}, Ticker: {res2.get('ticker')}, Period: {res2.get('period')}")
    assert res2.get("intent") == "CHART"
    assert res2.get("ticker") == "AAPL", f"Expected AAPL from context, got {res2.get('ticker')}"

    # Step C: Compare intent
    res3 = agent.process_message(test_user, subject="Comparison", body="Compare Microsoft vs Tesla")
    print(f"Step 3 Intent: {res3.get('intent')}, Tickers: {res3.get('tickers')}")
    assert res3.get("intent") == "COMPARE"
    assert "MSFT" in res3.get("tickers") and "TSLA" in res3.get("tickers")

    # Step D: General conversational greeting
    res4 = agent.process_message(test_user, subject="Hi", body="Good morning, who are you?")
    print(f"Step 4 Intent: {res4.get('intent')}")
    assert res4.get("intent") == "CHAT"

    print("✅ Agent intent and context tests passed!")


if __name__ == "__main__":
    test_ticker_matcher()
    test_context_storage()
    test_agent_intent_and_context_tracking()
    print("\n🎉 ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
