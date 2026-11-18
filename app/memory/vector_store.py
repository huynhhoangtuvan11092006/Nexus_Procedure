"""
NexusProcure AI - RAG Vectorstore Module.

Indexes historical procurement deals in ChromaDB to provide data-driven benchmarks
(past discounts, lead times, negotiation arguments) for Buyer and Reviewer agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.core.config import settings
from app.data.database import get_historical_deals

logger = logging.getLogger(__name__)


def build_benchmark_documents() -> List[Dict[str, Any]]:
    """
    Fetch all 50 historical deals from SQLite and format them into semantic documents.
    
    Each document contains:
    - Text representation optimized for vector search
    - Rich metadata for filtering by item_id or supplier_id
    """
    deals = get_historical_deals()
    documents = []

    for deal in deals:
        content = (
            f"Hợp đồng mua sắm #{deal['deal_id']} | "
            f"Mặt hàng: {deal['item_name']} (Mã: {deal['item_id']}) | "
            f"Nhà cung cấp: {deal['supplier_name']} | "
            f"Ngày ký kết: {deal['deal_date']} | "
            f"Số lượng: {deal['quantity']} chiếc | "
            f"Đơn giá chốt: {deal['unit_price_vnd']:,.0f} VNĐ | "
            f"Tỷ lệ chiết khấu: {deal['discount_pct']}% | "
            f"Thời hạn giao hàng: {deal['lead_time_days']} ngày | "
            f"Điều khoản thanh toán: {deal['payment_terms']} | "
            f"Thời hạn bảo hành: {deal['warranty_months']} tháng | "
            f"Kết quả thương lượng: {deal['deal_outcome']} | "
            f"Ghi chú: {deal['notes']}"
        )

        metadata = {
            "deal_id": int(deal["deal_id"]),
            "item_id": str(deal["item_id"]),
            "supplier_id": str(deal["supplier_id"]),
            "quantity": int(deal["quantity"]),
            "unit_price_vnd": float(deal["unit_price_vnd"]),
            "discount_pct": float(deal["discount_pct"]),
            "lead_time_days": int(deal["lead_time_days"]),
            "deal_date": str(deal["deal_date"]),
        }

        documents.append({
            "id": f"deal_{deal['deal_id']}",
            "text": content,
            "metadata": metadata,
        })

    return documents


class BenchmarkVectorStore:
    """Manages persistent ChromaDB vector collection for procurement benchmarks."""

    COLLECTION_NAME = "procurement_benchmarks"

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        self._client = None
        self._collection = None

    def _init_chroma(self):
        """Lazy initialization of ChromaDB persistent client."""
        if self._collection is not None:
            return

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"description": "Historical procurement benchmark records"},
            )
        except Exception as e:
            logger.warning("[RAG] ChromaDB initialization warning: %s", e)
            self._collection = None

    def index_deals(self, force_reload: bool = False) -> int:
        """
        Index 50 historical deals into ChromaDB.
        Skips if collection already has documents unless force_reload=True.
        """
        self._init_chroma()
        if self._collection is None:
            logger.warning("[RAG] ChromaDB not available. Falling back to SQL queries.")
            return 0

        current_count = self._collection.count()
        if current_count > 0 and not force_reload:
            logger.info("[RAG] ChromaDB collection already populated with %d documents.", current_count)
            return current_count

        docs = build_benchmark_documents()
        ids = [d["id"] for d in docs]
        texts = [d["text"] for d in docs]
        metadatas = [d["metadata"] for d in docs]

        if force_reload and current_count > 0:
            self._collection.delete(ids=ids)

        self._collection.add(ids=ids, documents=texts, metadatas=metadatas)
        logger.info("[RAG] Successfully indexed %d historical deals into ChromaDB.", len(docs))
        return len(docs)

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        item_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top-k most relevant historical benchmark deals.
        
        Supports optional metadata filtering by item_id (e.g. COMP-STM32F4).
        Falls back to direct SQLite query if ChromaDB is unavailable.
        """
        self._init_chroma()

        if self._collection is not None:
            try:
                where_filter = {"item_id": item_id} if item_id else None
                results = self._collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where=where_filter,
                )

                retrieved = []
                if results and "documents" in results and results["documents"]:
                    docs = results["documents"][0]
                    metas = results["metadatas"][0] if "metadatas" in results else [{}] * len(docs)
                    ids = results["ids"][0] if "ids" in results else [""] * len(docs)

                    for doc_id, text, meta in zip(ids, docs, metas):
                        retrieved.append({
                            "id": doc_id,
                            "content": text,
                            "metadata": meta,
                        })
                return retrieved

            except Exception as e:
                logger.warning("[RAG] Chroma query error: %s. Using SQLite fallback.", e)

        # Fallback to direct SQLite retrieval
        return self._fallback_sql_retrieve(item_id, top_k)

    def _fallback_sql_retrieve(self, item_id: Optional[str], top_k: int) -> List[Dict[str, Any]]:
        """Reliable SQL fallback if ChromaDB is not yet initialized."""
        deals = get_historical_deals(item_id=item_id)
        results = []
        for deal in deals[:top_k]:
            text = (
                f"Hợp đồng mua sắm #{deal['deal_id']}: {deal['item_name']} từ {deal['supplier_name']} "
                f"ngày {deal['deal_date']}. SL: {deal['quantity']} chiếc, Giá: {deal['unit_price_vnd']:,.0f} đ, "
                f"Chiết khấu: {deal['discount_pct']}%, Hạn giao: {deal['lead_time_days']} ngày, "
                f"Điều khoản: {deal['payment_terms']}. Kết quả: {deal['deal_outcome']}"
            )
            results.append({
                "id": f"deal_{deal['deal_id']}",
                "content": text,
                "metadata": {
                    "deal_id": deal["deal_id"],
                    "item_id": deal["item_id"],
                    "unit_price_vnd": deal["unit_price_vnd"],
                    "discount_pct": deal["discount_pct"],
                },
            })
        return results


# Global singleton instance
benchmark_store = BenchmarkVectorStore()


def retrieve_price_benchmarks(
    query: str,
    top_k: int = 3,
    item_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convenience helper function for agents to query procurement benchmarks."""
    return benchmark_store.retrieve(query=query, top_k=top_k, item_id=item_id)


def index_all_benchmarks(force_reload: bool = False) -> int:
    """Populate vector database with all 50 historical deals."""
    return benchmark_store.index_deals(force_reload=force_reload)

