"""Runner for test suite"""
from test_bot import test_directives, test_process_message_pipeline

if __name__ == "__main__":
    test_directives()
    test_process_message_pipeline()
