"""ArangoDB 접근 추상화. case 저장/조회, vector search, graph traversal."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from arango.database import StandardDatabase
from arango.exceptions import AQLQueryExecuteError

from app.config import Settings
from app.db import queries
from app.models.schemas import SimilarCase

logger = logging.getLogger(__name__)


class CaseRepository:
    def __init__(self, db: StandardDatabase, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # ---------- write ----------
    def insert_case(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        coll = self.db.collection("xray_cases")
        if "_key" in doc and coll.has(doc["_key"]):
            coll.update(doc)
            return coll.get(doc["_key"])
        return coll.insert(doc, return_new=True)["new"]

    def add_case_disease(self, case_key: str, disease_key: str, *, confidence: float = 1.0,
                         source: str = "ground_truth") -> None:
        edge_key = f"{case_key}__{disease_key}"
        edge = {
            "_key": edge_key,
            "_from": f"xray_cases/{case_key}",
            "_to": f"diseases/{disease_key}",
            "confidence": confidence,
            "source": source,
        }
        coll = self.db.collection("case_has_disease")
        if coll.has(edge_key):
            coll.update(edge)
        else:
            coll.insert(edge)

    def add_case_finding(self, case_key: str, finding_key: str, score: float = 0.8) -> None:
        edge_key = f"{case_key}__{finding_key}"
        edge = {
            "_key": edge_key,
            "_from": f"xray_cases/{case_key}",
            "_to": f"findings/{finding_key}",
            "score": score,
        }
        coll = self.db.collection("case_has_finding")
        # finding 문서 자동 생성(seed 외 새 finding 대비)
        f_coll = self.db.collection("findings")
        if not f_coll.has(finding_key):
            f_coll.insert({"_key": finding_key, "name": finding_key,
                           "description": "auto-generated finding"})
        if coll.has(edge_key):
            coll.update(edge)
        else:
            coll.insert(edge)

    def add_case_roi_anomaly(self, case_key: str, roi_key: str, *,
                             mean_error: float, p95_error: float, severity: str) -> None:
        edge_key = f"{case_key}__{roi_key}"
        edge = {
            "_key": edge_key,
            "_from": f"xray_cases/{case_key}",
            "_to": f"rois/{roi_key}",
            "meanError": mean_error,
            "p95Error": p95_error,
            "severity": severity,
        }
        coll = self.db.collection("case_has_roi_anomaly")
        if coll.has(edge_key):
            coll.update(edge)
        else:
            coll.insert(edge)

    # ---------- read ----------
    #: 케이스 하나에 매달리는 간선 컬렉션. 케이스를 덮어쓸 때 함께 지워야
    #: 하는 것들이고, 분류 체계(diseases/findings/rois 와 그 사이의 간선)는
    #: 여기 없다 - 그쪽은 케이스와 무관하게 존재한다.
    CASE_EDGE_COLLECTIONS = ("case_has_disease", "case_has_finding", "case_has_roi_anomaly")

    def delete_case_edges(self, case_key: str) -> int:
        """이 케이스에서 나가는 간선을 모두 지운다.

        같은 키로 다시 등록할 때 필요하다. 간선 키가 case_key 에서 유도되므로
        같은 태그는 덮어써지지만, **없어진 태그의 간선은 그대로 남는다** -
        예를 들어 --uncertainty 정책을 바꿔 재적재하면 예전 정책에서만 붙던
        병명이 그래프에 계속 매달려 있게 된다. 그 잔재를 여기서 끊는다.
        """
        removed = 0
        for name in self.CASE_EDGE_COLLECTIONS:
            coll = self.db.collection(name)
            for edge in coll.find({"_from": f"xray_cases/{case_key}"}):
                coll.delete(edge["_key"])
                removed += 1
        return removed

    def reset_cases(self) -> Dict[str, int]:
        """케이스와 그 간선을 전부 비운다. 분류 체계는 건드리지 않는다.

        적재 스크립트의 --reset 이 쓴다. 반환값은 컬렉션별로 지운 문서 수다 -
        무엇이 사라졌는지 요약에 남기기 위한 것이고, 호출자가 확인하지 않아도
        되는 부수효과로 두지 않는다.
        """
        removed: Dict[str, int] = {}
        for name in ("xray_cases",) + self.CASE_EDGE_COLLECTIONS:
            coll = self.db.collection(name)
            removed[name] = coll.count()
            coll.truncate()
        return removed

    def get_case(self, case_key: str) -> Optional[Dict[str, Any]]:
        coll = self.db.collection("xray_cases")
        if not coll.has(case_key):
            return None
        return coll.get(case_key)

    # ---------- search ----------
    def vector_search(
        self,
        field: str,
        embedding: Iterable[float],
        *,
        view: Optional[str] = None,
        model_version: Optional[str] = None,
        mask_version: Optional[str] = None,
        top_k: int = 20,
    ) -> List[SimilarCase]:
        params = {
            "field": field,
            "queryEmbedding": list(embedding),
            "view": view,
            "modelVersion": model_version,
            "maskVersion": mask_version,
            "nProbe": self.settings.VECTOR_NPROBE,
            "topK": int(top_k),
        }
        try:
            cursor = self.db.aql.execute(queries.VECTOR_SEARCH_AQL, bind_vars=params)
        except AQLQueryExecuteError as e:
            logger.warning("Vector AQL not supported (%s); falling back to brute-force cosine", e)
            # fallback 쿼리는 nProbe 를 참조하지 않으므로 strict bind 검사에 걸리지 않게 제거
            fallback_params = {k: v for k, v in params.items() if k != "nProbe"}
            cursor = self.db.aql.execute(
                queries.VECTOR_SEARCH_FALLBACK_AQL, bind_vars=fallback_params
            )
        return [SimilarCase(**row) for row in cursor]

    # ---------- graph ----------
    def graph_traversal(self, case_keys: List[str]) -> List[Dict[str, Any]]:
        if not case_keys:
            return []
        params = {"similarCaseIds": case_keys, "graphName": self.settings.ARANGO_GRAPH_NAME}
        try:
            return list(self.db.aql.execute(queries.GRAPH_TRAVERSAL_AQL, bind_vars=params))
        except Exception as e:  # pragma: no cover
            logger.warning("graph_traversal failed: %s", e)
            return []

    def add_feedback(self, case_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        coll_name = "case_feedback"
        if not self.db.has_collection(coll_name):
            self.db.create_collection(coll_name)
        doc = dict(payload)
        doc.setdefault("caseId", case_key)
        return self.db.collection(coll_name).insert(doc, return_new=True)["new"]
