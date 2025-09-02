from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from ratelimit import apply_rate_limit
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, select

# SQLAlchemy ORM (Object Relational Mapping) is generally the industry standard for database interaction.
# https://stackoverflow.com/questions/1279613/what-is-an-orm-how-does-it-work-and-how-should-i-use-one
#
# Without ORM, you would do something like this:
#
# book_list = new List();
# sql = "SELECT book FROM library WHERE author = 'Linus'";
# data = query(sql);
# while (row = data.next())
# {
#      book = new Book();
#      book.setAuthor(row.get('author');
#      book_list.add(book);
# }
#
# With an ORM library, it would look like this:
# book_list = BookTable.query(author="Linus");

# Alternatively, raw SQL:
# import psycopg2
#
# conn = psycopg2.connect("dbname=fastapi_demo user=postgres password=gloryness host=localhost")
# cur = conn.cursor()
#
# cur.execute("INSERT INTO items (text, is_done) VALUES (%s, %s) RETURNING id", ("apple", False))
# item_id = cur.fetchone()[0]
#
# conn.commit()
# cur.close()
# conn.close()

# FastAPI, unlike Flask or Django, has interactive documentation.
# http://127.0.0.1:8000/docs#
# http://127.0.0.1:8000/redoc
# FastAPI is async by default , easier to use , and obviously lightweight.

# Writing def route("/") : FastAPI runs in a threadpool behind the scenes, so it won't block the event loop completely. Not true ASYNC. -> good for CPU-bound logic
# Writing async def route("/") : FastAPI runs it directly in the event loop - true ASYNC, non-blocking. -> good for I/O (DB queries, HTTP requests, file io)

# In command line to run a local server:
# uvicorn main:app --reload

# https://www.postgresql.org/download/windows/
DATABASE_URL = "postgresql+psycopg://postgres:gloryness@localhost:5432/fastapi_demo"
engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session

# SQLAlchemy Model (table)
class ItemDB(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

# Pydantic Schema
# BASE SCHEMA for Inheritance
class ItemBase(BaseModel):
    # Using pydantic models means data gets sent through JSON data of the request instead of query parameters.
    text: str = None
    is_done: bool = False

# REQUEST SCHEMA : What the client SENDS when creating an item
class ItemCreate(ItemBase):
    text: str # required on create

# REQUEST SCHEMA : What the client SENDS when updating an item
class ItemUpdate(ItemBase):
    text: str = None # required on create
    is_done: bool = False

# RESPONSE SCHEMA : What the client RECEIVES (text, is_done + id)
class ItemOut(ItemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
    # class Config: # DEPRECATED
    #     orm_mode = True # lets FastAPI convert from SQLAlchemy object

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # create tables if not already created
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

items = []

@app.get("/")
def root():
    return {"Hello": "World"}

# curl -X POST -H "Content-Type: application/json" -d "{\"text\":\"apple\"}" "http://127.0.0.1:8000/items"
@app.post("/items", response_model=ItemOut)
async def create_item(item: ItemCreate, db: AsyncSession = Depends(get_db)):
    apply_rate_limit("global_unauthenticated_user")
    # items.append(item)
    new_item = ItemDB(text=item.text, is_done=item.is_done)
    db.add(new_item)
    await db.commit() # After commit , the SQLAlchemy object in memory doesn't automatically get updated with the auto-generated values like id or timestamps.
    # new_item.id is not accessible here
    await db.refresh(new_item) # .refresh() runs a SELECT under the hood to re-load the object's fields from the database.
    # At this point new_item.id is accessible
    return new_item

@app.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: int, updates: ItemUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ItemDB).where(ItemDB.id == item_id))
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    # exclude_unset: Whether to exclude fields that have not been explicitly set.
    for field, value in updates.dict(exclude_unset=True).items():
        setattr(db_item, field, value)

    await db.commit()
    return db_item


@app.get("/items", response_model=list[ItemOut])
async def list_items(limit: int = 10, db: AsyncSession = Depends(get_db)): # 'limit' is a query parameter (e.g. ?limit=1)
    apply_rate_limit("global_unauthenticated_user")
    result = await db.execute(select(ItemDB).limit(limit))
    return result.scalars().all()

@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    apply_rate_limit("global_unauthenticated_user")
    result = await db.execute(select(ItemDB).where(ItemDB.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ItemDB).where(ItemDB.id == item_id))
    db_item = result.scalar_one_or_none()

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(db_item)
    await db.commit()
    return None