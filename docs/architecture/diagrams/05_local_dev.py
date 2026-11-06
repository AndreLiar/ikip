"""IKIP local development topology (NFR17) — Docker Compose; only AI calls are remote."""
import os

from diagrams import Diagram, Cluster
from diagrams.onprem.client import User
from diagrams.programming.framework import NextJs, FastAPI
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.generic.storage import Storage
from diagrams.onprem.workflow import Airflow          # semantic -> Dagster
from diagrams.azure.ml import AzureOpenAI

from _theme import graph_attr, node_attr, edge_attr, principal, backing, cluster

OUT = os.path.join(os.path.dirname(__file__), "..", "img", "05_local_dev")

with Diagram("IKIP — Local Development (Docker Compose)", filename=OUT,
             outformat=["png", "svg"], show=False, direction="LR",
             graph_attr=graph_attr, node_attr=node_attr, edge_attr=edge_attr):

    dev = User("Developer\nlocalhost")

    with Cluster("Docker Compose  (laptop · 16 GB · no GPU)", graph_attr=cluster("#eef3fb")):
        web = NextJs("web :3000")
        api = FastAPI("api :8000")
        pg = PostgreSQL("postgres + pgvector :5432")
        redis = Redis("redis :6379")
        dagster = Airflow("Dagster")

    with Cluster("Remote (HTTPS only)", graph_attr=cluster("#fdf4e7")):
        r2 = Storage("Cloudflare R2\n(S3 object storage ·\nMinIO optional offline)")
        llm = AzureOpenAI("Azure OpenAI\n(LLM + embeddings)")

    dev >> principal("browses") >> web
    web >> principal("calls /api/v1") >> api
    api >> principal("queries") >> pg
    dagster >> principal("writes curated") >> pg

    api >> backing("enqueue") >> redis
    dagster >> backing("jobs") >> redis

    api >> backing("objects (HTTPS)") >> r2
    dagster >> backing("artifacts (HTTPS)") >> r2
    api >> principal("routes-to-LLM (HTTPS)") >> llm
    dagster >> backing("embeddings (HTTPS)") >> llm
