"""
NexusProcure - Pydantic Data Models & Schemas.

Defines structured outputs for:
- BuyerOffer (Buyer Agent with RAG grounding)
- SellerOffer (Seller Agent with cost/floor constraints)
- MediatorDecision (Mediator Agent convergence & arbitration)
- HumanAction (Human-in-the-Loop inputs)
- PurchaseOrder (Executive Sign-off Certificate)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PriorityType(str, Enum):
    BALANCED = "BALANCED"
    FAST_DELIVERY = "FAST_DELIVERY"
    LOWEST_COST = "LOWEST_COST"


class ManagerDecisionType(str, Enum):
    APPROVE_RECOMMENDED = "APPROVE_RECOMMENDED"
    SELECT_ALTERNATIVE = "SELECT_ALTERNATIVE"
    TERMINATE = "TERMINATE"


class BuyerOffer(BaseModel):
    """Structured output emitted by Strategic Buyer Agent."""
    offer_price: float = Field(..., description="Mức giá mua đề xuất (Đơn vị tiền tệ chuẩn)")
    reasoning: str = Field(..., description="Lập luận thuyết phục bằng 100% TIẾNG VIỆT (Tuyệt đối không dùng tiếng Anh)")
    concessions_made: List[str] = Field(default_factory=list, description="Danh sách các nhượng bộ bằng 100% TIẾNG VIỆT")
    benchmark_references: List[str] = Field(default_factory=list, description="Căn cứ lịch sử RAG bằng 100% TIẾNG VIỆT")
    lead_time_days: int = Field(default=7, description="Thời gian giao hàng yêu cầu (ngày)")
    payment_terms: str = Field(default="Net 15", description="Điều khoản thanh toán đề xuất")
    engine: str = Field(default="LLM", description="Engine thực thi: 'LLM' hoặc 'HEURISTIC'")
    api_warning: Optional[str] = Field(default=None, description="Cảnh báo nếu chạm hạn ngạch API hoặc lỗi mạng")


class SellerOffer(BaseModel):
    """Structured output emitted by Supplier Simulator Agent."""
    offer_price: float = Field(..., description="Mức giá bán chào hàng mới nhất")
    reasoning: str = Field(..., description="Lập luận bảo vệ giá bằng 100% TIẾNG VIỆT (Tuyệt đối không dùng tiếng Anh)")
    concessions_made: List[str] = Field(default_factory=list, description="Mức giảm giá hoặc ưu đãi bằng 100% TIẾNG VIỆT")
    lead_time_days: int = Field(default=7, description="Thời gian giao hàng cam kết (ngày)")
    payment_terms: str = Field(default="Net 30", description="Điều khoản thanh toán mong muốn")
    warranty_months: int = Field(default=12, description="Thời hạn bảo hành (tháng)")
    engine: str = Field(default="LLM", description="Engine thực thi: 'LLM' hoặc 'HEURISTIC'")
    api_warning: Optional[str] = Field(default=None, description="Cảnh báo nếu chạm hạn ngạch API hoặc lỗi mạng")


class MediatorDecision(BaseModel):
    """Evaluation result computed by Mediator Agent."""
    status: str = Field(..., description="CONTINUE, SUCCESS, PAUSED, DEADLOCK, TERMINATED")
    price_gap: float = Field(..., description="Khoảng cách giá tuyệt đối (seller_ask - buyer_bid)")
    price_gap_pct: float = Field(..., description="Tỷ lệ chênh lệch giá (%) so với giá bán")
    reasoning: str = Field(..., description="Nhận định của trọng tài về tiến trình hội tụ")
    requires_human: bool = Field(default=False, description="Cần kích hoạt Human-in-the-Loop interrupt")


class HumanAction(BaseModel):
    """Input payload injected during Human Intervention."""
    action: str = Field(..., description="approve, reject, modify_buyer, modify_seller, inject")
    new_budget_ceiling: Optional[float] = None
    new_min_price: Optional[float] = None
    injected_guidance: Optional[str] = None


class PurchaseOrder(BaseModel):
    """Official generated Purchase Order certificate upon agreement."""
    po_number: str
    pr_id: Optional[str] = "PR-001"
    created_date: Optional[str] = None
    created_at: Optional[str] = None
    item_id: Optional[str] = None
    item_name: str
    supplier_id: Optional[str] = None
    supplier_name: str
    procured_quantity: Optional[int] = None
    quantity: Optional[int] = None
    final_unit_price_vnd: Optional[float] = None
    agreed_unit_price: Optional[float] = None
    total_amount_vnd: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "$"
    delivery_deadline: Optional[str] = None
    delivery_days: int = 7
    payment_terms: str = "Net 15"
    warranty_months: int = 12
    savings_vs_budget_vnd: Optional[float] = 0.0
    status: str = "APPROVED"
    manager_approval_note: Optional[str] = ""
    approval_note: Optional[str] = ""

    def model_post_init(self, __context: Any) -> None:
        if self.quantity is None and self.procured_quantity is not None:
            self.quantity = self.procured_quantity
        elif self.procured_quantity is None and self.quantity is not None:
            self.procured_quantity = self.quantity

        if self.agreed_unit_price is None and self.final_unit_price_vnd is not None:
            self.agreed_unit_price = self.final_unit_price_vnd
        elif self.final_unit_price_vnd is None and self.agreed_unit_price is not None:
            self.final_unit_price_vnd = self.agreed_unit_price

        if self.total_amount is None and self.total_amount_vnd is not None:
            self.total_amount = self.total_amount_vnd
        elif self.total_amount_vnd is None and self.total_amount is not None:
            self.total_amount_vnd = self.total_amount

        if self.created_at is None and self.created_date is not None:
            self.created_at = self.created_date
        elif self.created_date is None and self.created_at is not None:
            self.created_date = self.created_at


class NegotiationRoundRecord(BaseModel):
    round: int
    supplier_id: str
    supplier_name: str
    supplier_initial_ask: Dict[str, Any]
    buyer_counter_offer: Dict[str, Any]
    supplier_response_offer: Dict[str, Any]
    price_gap_pct: float
    status: str
    summary: str


# Backward-compatible ContractOffer schema for existing graph and test cases
class ContractOffer(BaseModel):
    unit_price_vnd: float = Field(..., description="Unit price per item")
    lead_time_days: int = Field(default=7, description="Delivery lead time in days")
    moq: int = Field(default=100, description="Minimum order quantity")
    payment_terms: str = Field(default="Net 30", description="Payment terms")
    warranty_months: int = Field(default=12, description="Warranty duration in months")
    reasoning: Optional[str] = Field(default=None, description="Reasoning narrative")
    concession_notes: Optional[str] = Field(default=None, description="Concession tracking")


class MultiAttributeScore(BaseModel):
    cost_score: float
    delivery_score: float
    terms_score: float
    risk_score: float
    total_utility: float


class SupplierEvaluation(BaseModel):
    supplier_id: str
    supplier_name: str
    final_offer: ContractOffer
    total_cost_vnd: float
    scores: MultiAttributeScore
    is_within_budget: bool
    is_on_time: bool
    risk_assessment: str
    recommendation_rank: int = 1

