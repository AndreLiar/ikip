"""IKIP system context — matches architecture.md 'High Level Project Diagram'.

Two pipelines, one data model: Dagster (batch) writes the knowledge base;
LangGraph (request-time) reads it. Infra behind interfaces (ADR 0003).
"""
import os

from diagrams import Diagram, Cluster
from diagrams.onprem.client import Users
from diagrams.programming.framework import NextJs, FastAPI
from diagrams.programming.language import Python
from diagrams.onprem.database import PostgreSQL
from diagrams.generic.storage import Storage
from diagrams.onprem.workflow import Airflow          # semantic: workflow orchestrator -> Dagster
from diagrams.azure.ml import AzureOpenAI
from diagrams.onprem.monitoring import Grafana

from _theme import graph_attr, node_attr, edge_attr, principal, backing, cluster

OUT = os.path.join(os.path.dirname(__file__), "..", "img", "01_system_context")

with Diagram("IKIP — System Context", filename=OUT, outformat=["png", "svg"],
             show=False, direction="LR",
             graph_attr=graph_attr, node_attr=node_attr, edge_attr=edge_attr):

    users = Users("Technicians / Admins")

    with Cluster("Documentation Sources", graph_attr=cluster("#eef3fb")):
        src = Storage("Manuals · SOPs ·\nCSV / Excel / API feeds")

    with Cluster("Data Engineering — Dagster (batch)", graph_attr=cluster("#eaf5ef")):
        dagster = Airflow("Dagster pipeline\ningest→parse/OCR→clean→dedup→\nversion→chunk→embed→index")

    with Cluster("Knowledge Base (shared, separable stores)", graph_attr=cluster("#fdf4e7")):
        pg = PostgreSQL("PostgreSQL 16 + pgvector\nmetadata · full-text · vectors")
        obj = Storage("Object storage\nraw / cleaned / curated")

    with Cluster("Application Layer", graph_attr=cluster("#eef3fb")):
        web = NextJs("Next.js Web App")
        api = FastAPI("FastAPI API")

    with Cluster("RAG Orchestration — LangGraph (request-time)", graph_attr=cluster("#f3ecf8")):
        rag = Python("LangGraph + LangChain\nanalyze→retrieve→rerank→\nsufficiency→cite / abstain")

    llm = AzureOpenAI("Azure OpenAI\nLLM + embeddings")
    obs = Grafana("Observability\n& Evaluation")

    # principal flows
    src >> principal("ingested by") >> dagster
    dagster >> principal("writes curated") >> pg
    dagster >> principal("stores artifacts") >> obj
    users >> principal("uses") >> web
    web >> principal("calls /api/v1") >> api
    api >> principal("invokes") >> rag
    rag >> principal("hybrid retrieval") >> pg
    rag >> principal("routes-to-LLM") >> llm
    rag >> principal("grounded answer") >> api

    # backing dependencies
    api >> backing("authorizes before retrieval") >> pg
    rag >> backing("fetches source pages") >> obj
    api >> backing("ships traces / metrics") >> obs
    rag >> backing("evaluated / traced") >> obs
