from pydantic import BaseModel


class Metric(BaseModel):
    label: str
    value: str
    hint: str


class ToolDefinition(BaseModel):
    id: str
    icon: str
    name: str
    desc: str
    status: str
    updated: str
    tags: list[str]
    integration_id: str | None = None


class JobSummary(BaseModel):
    id: str
    name: str
    tool: str
    status: str
    progress: int
    updated: str


class LibraryItem(BaseModel):
    id: str
    title: str
    type: str
    desc: str
    tags: list[str]


class IntegrationDefinition(BaseModel):
    id: str
    name: str
    desc: str
    kind: str
    status: str
    repo_url: str | None = None


class WorkbenchSnapshot(BaseModel):
    metrics: list[Metric]
    tools: list[ToolDefinition]
    jobs: list[JobSummary]
    library: list[LibraryItem]
    integrations: list[IntegrationDefinition]
