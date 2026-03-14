import subprocess
import sys
import json

def call_smithery(connection, tool, args_dict):
    cmd = [
        "smithery.cmd", "tool", "call", 
        connection, 
        tool, 
        json.dumps(args_dict, ensure_ascii=False)
    ]
    print(f"Executing: {' '.join(cmd)}")
    try:
        # shell=False is better on windows with list of args
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        print(f"Status: {result.returncode}")
        print("Output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python smithery_bridge.py <tool> <json_args>")
        sys.exit(1)
    
    tool_name = sys.argv[1]
    args_json = sys.argv[2]
    try:
        args_dict = json.loads(args_json)
    except:
        # Fallback if query style is used
        args_dict = {"query": args_json}
        
    call_smithery("kis-code-assistant-mcp", tool_name, args_dict)
