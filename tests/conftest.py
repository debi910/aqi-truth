import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

needs_db2 = pytest.mark.skipif(not os.getenv("DB2_PASSWORD"), reason="set DB2_PASSWORD to run against a real Db2")

@pytest.fixture(scope="session")
def conn():
    from db import connect
    c = connect()
    yield c
    c.close()
