import inspect
import pytest
from scripts import init_db

def test_init_db_exports_required_symbols():
    """
    Verification for Fix A10: Ensure required symbols for backend lifespan
    migration/bootstrapping are correctly exported and are async functions.
    """
    # 1. Verify init_database exists and is callable
    assert hasattr(init_db, "init_database"), "init_database missing from scripts.init_db"
    assert callable(init_db.init_database), "init_database is not callable"
    
    # 2. Verify bootstrap_users exists and is callable
    assert hasattr(init_db, "bootstrap_users"), "bootstrap_users missing from scripts.init_db"
    assert callable(init_db.bootstrap_users), "bootstrap_users is not callable"
    
    # 3. Verify both are coroutine functions (async def)
    # The backend lifespan uses await init_database() and await bootstrap_users()
    assert inspect.iscoroutinefunction(init_db.init_database), "init_database must be async def"
    assert inspect.iscoroutinefunction(init_db.bootstrap_users), "bootstrap_users must be async def"

@pytest.mark.unit
def test_init_db_symbols_runtime():
    """Wrapper for pytest marker support."""
    test_init_db_exports_required_symbols()
