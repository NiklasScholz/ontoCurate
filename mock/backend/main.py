from fastapi import FastAPI, File, UploadFile

app = FastAPI()


@app.post("/login")
async def login(username: str, password: str):
    return None


@app.post("/logout")
async def logout():
    return None


@app.get("/workspaces")
async def workspaces():
    return [{"name": "bar"}, {"name": "baz"}, {"name": "foo"}]


@app.post("/workspaces/create")
async def workspaces_create(name: str):
    return None


@app.delete("/workspaces/delete")
async def workspaces_delete(name: str):
    return None


@app.get("/documents")
async def documents(workspace: str):
    return [
        {
            "name": "a.pdf",
            "extractedCount": 51,
            "pendingCount": 0,
        },
        {
            "name": "b.pdf",
            "extractedCount": 42,
            "pendingCount": 0,
        },
        {
            "name": "c.pdf",
            "extractedCount": 49,
            "pendingCount": 12,
        },
    ]


@app.post("/documents/upload")
async def documents_upload(workspace: str, file: UploadFile = File()):
    return None


@app.delete("/documents/delete")
async def documents_delete(workspace: str, name: str):
    return None
