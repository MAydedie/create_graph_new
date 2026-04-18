
try:
    with open("test_result.log", "r", encoding="utf-16") as f:
        print(f.read())
except:
    try:
        with open("test_result.log", "r", encoding="utf-8") as f:
            print(f.read())
    except:
        with open("test_result.log", "r", encoding="gbk", errors="ignore") as f:
            print(f.read())
