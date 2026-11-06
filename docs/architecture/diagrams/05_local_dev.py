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
        minio = Storage("MinIO :9000\n(S3-compatible)")
        redis = Redis("redis :6379")
        dagster = Airflow("Dagster")

    llm = AzureOpenAI("Azure OpenAI\n(only remote dependency)")

    dev >> principal("browses") >> web
    web >> principal("calls /api/v1") >> api
    api >> principal("queries") >> pg
    dagster >> principal("writes curated") >> pg

    api >> backing("objects") >> minio
    api >> backing("enqueue") >> redis
    dagster >> backing("artifacts") >> minio
    dagster >> backing("jobs") >> redis

    api >> principal("routes-to-LLM (HTTPS)") >> llm
    dagster >> backing("embeddings (HTTPS)") >> llm
