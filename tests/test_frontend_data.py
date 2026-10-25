from aika.frontend_data import LocalKnowledgeGraph


def sample_graph() -> LocalKnowledgeGraph:
    return LocalKnowledgeGraph(
        entities=[
            {"type": "Company", "name": "浪潮信息", "normalized_name": "浪潮信息"},
            {"type": "Company", "name": "天孚通信", "normalized_name": "天孚通信"},
            {"type": "Technology", "name": "AI服务器", "normalized_name": "ai服务器"},
            {"type": "Report", "name": "AI服务器与光模块产业链专题", "normalized_name": "research_1"},
        ],
        relations=[
            {
                "head_type": "Company",
                "head_name": "浪潮信息",
                "relation": "USES_TECHNOLOGY",
                "tail_type": "Technology",
                "tail_name": "AI服务器",
                "evidence": "浪潮信息位于AI服务器产业链。",
                "source_title": "AI服务器与光模块产业链专题",
                "page": "11",
            },
            {
                "head_type": "Company",
                "head_name": "天孚通信",
                "relation": "USES_TECHNOLOGY",
                "tail_type": "Technology",
                "tail_name": "高速光器件",
                "evidence": "AI技术推动公司高速光器件市场持续增长。",
                "source_title": "AI服务器与光模块产业链专题",
                "page": "41",
            },
        ],
    )


def test_graph_filter_by_company() -> None:
    graph = sample_graph()

    rows = graph.subgraph_relations(company="天孚通信")

    assert len(rows) == 1
    assert rows[0]["head_name"] == "天孚通信"
