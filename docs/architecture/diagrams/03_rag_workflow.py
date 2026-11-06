"""IKIP RAG request workflow — LangGraph graph (Epic 3), authorize-before-retrieve + abstention."""
import os

from diagrams import Diagram, Cluster
from diagrams.onprem.client import Users, Client
from diagrams.programming.language import Python
from diagrams.onprem.database import PostgreSQL
from diagrams.azure.ml import AzureOpenAI

from _theme import graph_attr, node_attr, edge_attr, principal, backing, cluster

OUT = os.path.join(os.path.dirname(__file__), "..", "img", "03_rag_workflow")

with Diagram("IKIP — RAG Request Workflow (LangGraph)", filename=OUT,
             outformat=["png", "svg"], show=False, direction="LR",
             graph_attr=graph_attr, node_attr=node_attr, edge_attr=edge_attr):

    user = Users("Technician\n+ tenant / role")

    with Cluster("LangGraph graph (checkpointed, auditable)", graph_attr=cluster("#f3ecf8")):
        authz = Python("Authorize\n(before retrieval)")
        analyze = Python("Query\nanalysis")
        equip = Python("Equipment\nidentification")
        retrieve = Python("Hybrid retrieval\n+ equipment/version filters")
        rerank = Python("Rerank")
        suff = Python("Sufficiency\ncheck")
        gen = Python("Cited generation\n+ surface warnings")
        abstain = Python("Abstain:\ninsufficient evidence")

    pg = PostgreSQL("PostgreSQL + pgvector")
    llm = AzureOpenAI("Azure OpenAI")
    # LangChain is a library used *inside* the LangGraph nodes (model/retriever/tool/prompt
    # integrations), not a flow stage — so it appears as a backing dependency, not a step.
    lc = Python("LangChain\nmodel · retriever · tool ·\nprompt integrations")
    trace = Python("QueryTrace\nlatency · cost · ids")
    answer = Client("Answer + citations")
    deny = Client("403 Denied")

    user >> principal("asks") >> authz
    authz >> backing("unauthorized") >> deny
    authz >> principal("authorized") >> analyze
    analyze >> principal("intent") >> equip
    equip >> principal("filtered query") >> retrieve
    retrieve >> principal("candidates") >> rerank
    rerank >> principal("top-k") >> suff
    suff >> principal("sufficient") >> gen
    suff >> principal("insufficient") >> abstain
    gen >> principal("cited answer") >> answer
    abstain >> principal("honest refusal") >> answer

    retrieve >> backing("queries (authz-scoped)") >> pg
    gen >> backing("routes-to-LLM") >> llm
    gen >> backing("records") >> trace
    abstain >> backing("records") >> trace

    # nodes depend on LangChain integrations; LangChain in turn reaches the external resources
    for n in (retrieve, rerank, gen):
        n >> backing("uses integrations") >> lc
    lc >> backing("retriever / vector client") >> pg
    lc >> backing("model client") >> llm
