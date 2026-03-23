import subprocess
import os

def run():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path="../.env")
        
        # Build environment for the test process
        env = os.environ.copy()
        # Only set defaults if not already in env
        if "LLM_PROVIDER" not in env:
            env["LLM_PROVIDER"] = "none"
        if "LLM_API_KEY" not in env:
            env["LLM_API_KEY"] = "mock_key"
        if "DATABASE_URL" not in env:
            env["DATABASE_URL"] = "postgresql://mock:mock@localhost:5432/mock"
        
        import sys
        # Run the test script and capture its output (skip pycache)
        result = subprocess.run(
            [sys.executable, "-B", "e2e_test.py"],
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
