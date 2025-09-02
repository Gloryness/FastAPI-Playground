import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import asyncio
import sys
from main import app, Base, get_db

# To run, in the command line:
# pytest -v
# To include print output:
# pytest -v -s

# Windows event loop fix
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Create tables synchronously.. too many errors occured when doing this inside setup_database.
# Sort of funny that pytest is sort of causing more problems...
sync_engine = create_engine("postgresql+psycopg://postgres:gloryness@localhost:5432/fastapi_test")
Base.metadata.drop_all(sync_engine)
Base.metadata.create_all(sync_engine)

# Separate test DB (so it doesn’t touch dev DB)
DATABASE_URL = "postgresql+psycopg://postgres:gloryness@localhost:5432/fastapi_test"
engine_test = create_async_engine(DATABASE_URL, echo=True)
TestingSessionLocal = sessionmaker(engine_test, expire_on_commit=False, class_=AsyncSession)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_database():
    print("A") # Printed BEFORE tests begin
    yield # tests begin ...
    print("B") # Printed AFTER tests begin

@pytest.mark.asyncio
async def test_create_item():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/items", json={"text": "apple"})
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "apple"
    assert data["is_done"] is False
    assert data["id"] == 1

@pytest.mark.asyncio
async def test_list_items():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["text"] == "apple"

@pytest.mark.asyncio
async def test_delete_item():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/items/1")
    assert response.status_code == 204

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/items")
    data = response.json()
    assert len(data) == 0

@pytest.mark.asyncio
async def test_ratelimit():
    transport = ASGITransport(app=app)
    codes = []
    for i in range(5):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/items")
        codes.append(response.status_code)
    # Due to 3 requests sent in the tests before , the maximum is 5 in 30 seconds.
    # Hence should expect 2 200s and 3 429s.
    assert codes == [200, 200, 429, 429, 429]