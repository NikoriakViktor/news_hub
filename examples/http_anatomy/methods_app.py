"""CRUD над словником у пам'яті: семантика GET, POST, PUT, PATCH, DELETE без бази, щоб видно було лише HTTP."""
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="Items")
ITEMS: dict[int, dict] = {}


class ItemIn(BaseModel):            # повний стан: POST і PUT
    title: str
    description: str | None = None


class ItemPatch(BaseModel):         # часткова зміна: усі поля необов'язкові
    title: str | None = None
    description: str | None = None


class StrictItemIn(ItemIn):
    model_config = ConfigDict(extra="forbid")      # невідомі поля → 422, а не мовчки ігнорувати


class ItemOut(ItemIn):
    id: int


def get_or_404(item_id: int) -> dict:
    if item_id not in ITEMS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return ITEMS[item_id]


@app.get("/items")
def list_items(offset: int = 0, limit: int = 10) -> list[ItemOut]:
    return list(ITEMS.values())[offset: offset + limit]


@app.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, response: Response) -> ItemOut:
    item_id = max(ITEMS, default=0) + 1
    ITEMS[item_id] = {"id": item_id, **body.model_dump()}
    response.headers["Location"] = f"/items/{item_id}"        # де тепер живе створений ресурс
    return ItemOut(**ITEMS[item_id])


@app.post("/strict-items", status_code=status.HTTP_201_CREATED)
def create_strict(body: StrictItemIn) -> ItemOut:
    return create_item(ItemIn(**body.model_dump()), Response())


@app.get("/items/{item_id}")
def read_item(item_id: int) -> ItemOut:
    return ItemOut(**get_or_404(item_id))


@app.put("/items/{item_id}")
def replace_item(item_id: int, body: ItemIn) -> ItemOut:
    get_or_404(item_id)
    ITEMS[item_id] = {"id": item_id, **body.model_dump()}     # увесь стан — з тіла, навіть пропущені поля
    return ItemOut(**ITEMS[item_id])


@app.patch("/items/{item_id}")
def modify_item(item_id: int, body: ItemPatch) -> ItemOut:
    item = get_or_404(item_id)
    item.update(body.model_dump(exclude_unset=True))          # лише ті поля, які клієнт надіслав
    return ItemOut(**item)


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int) -> None:
    get_or_404(item_id)
    del ITEMS[item_id]
