from parsers.python_parser import PythonParser
from analysis.code_model import ProjectAnalysisReport
import os

test_file = "main.py"
print(f"Testing parser on: {test_file}")

from datetime import datetime
parser = PythonParser(".")
report = ProjectAnalysisReport(".", ".", datetime.now().isoformat())

try:
    print("Parsing file...")
    parser.parse_file(test_file, report)
    print("Parse complete.")
    
    print(f"Classes found: {report.get_class_count()}")
    print(f"Functions found: {len(report.functions)}")
    
    if report.functions:
        print(f"Sample function: {report.functions[0].name}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
