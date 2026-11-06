"""IKIP Azure production topology (Epic 6) — Container Apps + managed services."""
import os

from diagrams import Diagram, Cluster
from diagrams.onprem.client import Users
from diagrams.onprem.ci import GithubActions
from diagrams.azure.compute import ContainerApps, ContainerRegistries
from diagrams.azure.database import DatabaseForPostgresqlServers
from diagrams.generic.storage import Storage       # Cloudflare R2 (no built-in icon) — label authoritative
from diagrams.azure.integration import ServiceBus
from diagrams.azure.security import KeyVaults
from diagrams.azure.identity import ActiveDirectory
from diagrams.azure.ml import AzureOpenAI
from diagrams.azure.devops import ApplicationInsights

from _theme import graph_attr, node_attr, edge_attr, principal, backing, cluster

OUT = os.path.join(os.path.dirname(__file__), "..", "img", "04_azure_deployment")

with Diagram("IKIP — Azure Production Topology", filename=OUT,
             outformat=["png", "svg"], show=False, direction="LR",
             graph_attr=graph_attr, node_attr=node_attr, edge_attr=edge_attr):

    users = Users("Technicians / Admins")
    entra = ActiveDirectory("Microsoft Entra ID")

    with Cluster("Azure Container Apps", graph_attr=cluster("#eef3fb")):
        web = ContainerApps("Web (Next.js)")
        api = ContainerApps("API (FastAPI)")
        workers = ContainerApps("Workers")
        jobs = ContainerApps("Container Apps Jobs\n(Dagster batch)")

    with Cluster("Data & Messaging", graph_attr=cluster("#fdf4e7")):
        pg = DatabaseForPostgresqlServers("PostgreSQL Flexible Server\n+ pgvector")
        blob = Storage("Cloudflare R2\n(S3, zero egress)")
        bus = ServiceBus("Service Bus")

    llm = AzureOpenAI("Azure OpenAI\nLLM + embeddings")

    with Cluster("Platform Services", graph_attr=cluster("#eaf5ef")):
        kv = KeyVaults("Key Vault")
        acr = ContainerRegistries("Container Registry")
        mon = ApplicationInsights("Azure Monitor /\nApp Insights")

    gha = GithubActions("GitHub Actions\nCI/CD")

    # principal request path
    users >> principal("authenticates") >> entra
    users >> principal("HTTPS") >> web
    web >> principal("calls /api/v1") >> api
    api >> principal("hybrid retrieval") >> pg
    api >> principal("routes-to-LLM") >> llm
    api >> principal("enqueue jobs") >> bus
    bus >> principal("triggers") >> workers
    jobs >> principal("writes curated") >> pg
    jobs >> principal("stores artifacts") >> blob

    # CI/CD
    gha >> principal("builds · pushes") >> acr
    gha >> principal("deploys") >> api
    acr >> backing("image") >> web
    acr >> backing("image") >> jobs

    # backing dependencies
    entra >> backing("authorizes") >> api
    kv >> backing("supplies-secrets") >> api
    kv >> backing("supplies-secrets") >> jobs
    api >> backing("reads / writes") >> blob
    for svc in (web, api, workers, jobs):
        svc >> backing("ships logs / traces") >> mon
