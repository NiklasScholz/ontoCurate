import json

from fastapi import FastAPI, File, UploadFile

app = FastAPI()

with open("input.md", "r") as file:
    MARKDOWN = file.read()

with open("provenance.json", "r") as file:
    JSON = json.load(file)


@app.post("/login")
async def login(username: str, password: str):
    return None


@app.post("/logout")
async def logout():
    return None


@app.get("/workspaces")
async def workspaces():
    return [{"name": "dev-test"}, {"name": "baz"}, {"name": "foo"}]


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
            "name": "paper1.pdf",
            "extractedCount": 1253,
            "pendingCount": 1234,
        },
        {
            "name": "paper2.pdf",
            "extractedCount": 1451,
            "pendingCount": 1451,
        },
        {
            "name": "paper3.pdf",
            "extractedCount": 556,
            "pendingCount": 556,
        },
    ]


@app.post("/documents/upload")
async def documents_upload(workspace: str, file: UploadFile = File()):
    return None


@app.delete("/documents/delete")
async def documents_delete(workspace: str, name: str):
    return None


@app.get("/documents/get")
async def documents_get(workspace: str, name: str):
    return {"text": MARKDOWN, "annotations": JSON["annotations"]}


@app.get("/kg/neighborhood")
async def kg_neighborhood(entity: str):
    incoming = []
    outgoing = []
    for triple in JSON["annotations"]:
        if triple["value"] == entity:
            incoming.append(
                {
                    "edge": triple["predicate"],
                    "node": triple["subject"],
                }
            )
        if triple["subject"] == entity:
            outgoing.append(
                {
                    "edge": triple["predicate"],
                    "node": triple["value"],
                }
            )
    return {"incoming": incoming, "outgoing": outgoing}
