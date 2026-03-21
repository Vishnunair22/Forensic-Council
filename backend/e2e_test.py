import asyncio
import secrets
from pathlib import Path
import sys
import logging
import struct
import os

# Set fallback environment for local code testing
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = "mock_key"
os.environ["DATABASE_URL"] = "postgresql://mock:mock@localhost:5432/mock"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["QDRANT_URL"] = "http://localhost:6333"

# Ensure backend modules can be imported
sys.path.insert(0, str(Path(__file__).parent))

from orchestration.pipeline import ForensicCouncilPipeline
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("e2e_output.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def run_e2e_test():
    logger.info("Initializing Code-Level E2E Pipeline Test")
    
    # Generate test image (minimal valid JPEG header)
    test_image_path = Path("e2e_test_image.jpg")
    minimal_jpeg = b'\xFF\xD8\xFF\xE0\x00\x10\x4A\x46\x49\x46\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00\xFF\xDB\x00\x43\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08\x0A\x0C\x14\x0D\x0C\x0B\x0B\x0C\x19\x12\x13\x0F\x14\x1D\x1A\x1F\x1E\x1D\x1A\x1C\x1C\x20\x24\x2E\x27\x20\x22\x2C\x23\x1C\x1C\x28\x37\x29\x2C\x30\x31\x34\x34\x34\x1F\x27\x39\x3D\x38\x32\x3C\x2E\x33\x34\x32\xFF\xC0\x00\x0B\x08\x00\x01\x00\x01\x01\x01\x11\x00\xFF\xC4\x00\x1F\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\xFF\xDA\x00\x08\x01\x01\x00\x00\x3F\x00\x37\xFF\xD9'
    test_image_path.write_bytes(minimal_jpeg)
    
    pipeline = ForensicCouncilPipeline()
    case_id = f"E2E-TEST-{secrets.token_hex(4)}"
    investigator_id = "test_agent"
    
    try:
        logger.info("Running complete pipeline (initial + deep + arbiter synthesis)...")
        report = await pipeline.run_investigation(
            evidence_file_path=str(test_image_path),
            case_id=case_id,
            investigator_id=investigator_id,
            original_filename="e2e_test_image.jpg"
        )
        
        logger.info("\n================= E2E PIPELINE REPORT =================")
        logger.info(f"Report ID: {report.report_id}")
        logger.info(f"Case ID  : {report.case_id}")
        logger.info("Synthesis Conclusion:")
        print(f"\n{report.synthesis}\n")
        
        logger.info("Agent Tracking & Compilations:")
        # Because we added _assign_severity_tier to the API, let's verify if findings contain expected keys
        # We manually apply the `api/routes/investigation.py` severity assignment to simulate API structure parsing
        from api.routes.investigation import _assign_severity_tier
        
        inconsistencies = False
        for agent, findings in report.per_agent_findings.items():
            print(f" ► {agent} Output: {len(findings)} findings")
            for f in findings:
                sev = _assign_severity_tier(f)
                tool = f.get('metadata', {}).get('tool_name', 'Unknown')
                print(f"    - Tool: {tool:<20} | Severity: {sev:<8} | Confidence: {f.get('confidence_raw', 0.0):.2f}")
                if 'metadata' not in f or 'description' not in f:
                    logger.error(f"Inconsistency detected: Missing required fields in {agent} finding -> {f}")
                    inconsistencies = True
                    
        if inconsistencies:
            logger.error("\nTEST FAILED: Findings had missing fields or inconsistencies!")
            sys.exit(1)
            
        logger.info("\n✅ E2E Pipeline executing properly. All agents and arbiter compilations returned valid structured results.")
        
    except Exception as e:
        logger.error(f"E2E Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if test_image_path.exists():
            test_image_path.unlink()

if __name__ == "__main__":
    # Windows needs specific loop policy sometimes if performing child processes
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_e2e_test())
