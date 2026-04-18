import sys
import os

print(f"SYS.PATH: {sys.path}")
try:
    import finance_cli
    print(f"Successfully imported finance_cli from {finance_cli.__file__}")
except ImportError as e:
    print(f"Failed to import finance_cli: {e}")
except Exception as e:
    print(f"Error: {e}")
