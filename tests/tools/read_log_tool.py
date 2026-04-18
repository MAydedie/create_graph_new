
import sys

def read_log():
    try:
        # Try UTF-16LE first as PowerShell redirect often makes it so
        filename = sys.argv[1] if len(sys.argv) > 1 else "server_debug.log"
        with open(filename, "r", encoding="gbk", errors="replace") as f:
            content = f.read()
            print(content) # Print ALL chars
    except UnicodeError:
        try:
            # Fallback to UTF-8
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                print(content)
        except Exception as e:
            print(f"Error reading log: {e}")
            # Try raw
            try:
                with open(filename, "rb") as f:
                    print(f.read()[-2000:])
            except:
                pass

if __name__ == "__main__":
    read_log()
