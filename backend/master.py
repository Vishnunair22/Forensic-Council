import subprocess
import os

def run():
    try:
        # Build environment for the test process
        env = os.environ.copy()
        env["LLM_PROVIDER"] = "none"
        env["LLM_API_KEY"] = "mock_key"
        env["DATABASE_URL"] = "postgresql://mock:mock@localhost:5432/mock"
        env["REDIS_URL"] = "redis://localhost:6379/0"
        env["QDRANT_URL"] = "http://localhost:6333"
        env["SIGNING_KEY"] = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        
        # Run the test script and capture its output (skip pycache)
        result = subprocess.run(
            [r"d:\Forensic Council\backend\.venv\Scripts\python.exe", "-B", "e2e_test.py"],
            capture_output=True,
            text=True,
            env=env
        )
        
        # Write the captured output directly to disk so we can read it reliably
        with open("master_out.txt", "w", encoding="utf-8") as f:
            f.write(f"EXIT_CODE: {result.returncode}\n")
            f.write("============ STDOUT ============\n")
            f.write(result.stdout)
            f.write("\n============ STDERR ============\n")
            f.write(result.stderr)
            
    except Exception as e:
        with open("master_out.txt", "w", encoding="utf-8") as f:
            f.write(f"SUBPROCESS FAILED: {str(e)}\n")

if __name__ == "__main__":
    run()
