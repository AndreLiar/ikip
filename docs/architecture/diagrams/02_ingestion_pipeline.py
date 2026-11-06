"""IKIP data-engineering pipeline — Dagster raw->curated assets (Epic 2)."""
import os

from diagrams import Diagram, Cluster
from diagrams.generic.storage import Storage
from diagrams.programming.language import Python
from diagrams.onprem.database import PostgreSQL

from _theme import graph_attr, node_attr, edge_attr, principal, backing, cluster

OUT = os.path.join(os.path.dirname(__file__), "..", "img", "02_ingestion_pipeline")

with Diagram("IKIP — Data Engineering Pipeline (Dagster, raw→curated)", filename=OUT,
             outformat=["png", "svg"], show=False, direction="LR",
             graph_attr=graph_attr, node_attr=node_attr, edge_attr=edge_attr):

    src = Storage("Sources\n(Category 1 manuals)")

    with Cluster("Dagster Orchestration  (schedules · sensors · lineage · backfills)",
                 graph_attr=cluster("#eaf5ef")):
        connect = Python("Connectors /\nscheduled sync")
        parse = Python("Parse + OCR fallback\nPyMuPDF · Docling · Tesseract")
        clean = Python("Clean · normalize ·\nvalidate (Pandera)")
        dedup = Python("Dedup +\nversion")
        enrich = Python("Metadata\nenrichment")
        chunk = Python("Structure-aware\nchunking")
        embed = Python("Embeddings\n(versioned)")
        index = Python("Index:\nfull-text + pgvector")

    obj = Storage("Object storage\nraw / cleaned / curated")
    pg = PostgreSQL("PostgreSQL + pgvector")
    dlq = Python("Dead-letter\n+ retry")
    report = Python("Data-quality\nreport")

    src >> principal("fetch") >> connect
    connect >> principal("store raw") >> obj
    connect >> principal("extract") >> parse
    parse >> principal("clean") >> clean
    clean >> principal("dedup") >> dedup
    dedup >> principal("enrich") >> enrich
    enrich >> principal("chunk") >> chunk
    chunk >> principal("embed") >> embed
    embed >> principal("index") >> index
    index >> principal("writes") >> pg

    parse >> backing("curated artifacts") >> obj
    clean >> backing("on failure") >> dlq
    dedup >> backing("quality metrics") >> report
