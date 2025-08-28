from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

class TicketStatus(str, Enum):
    new = "new"
    open = "open"
    in_progress = "in_progress"
    on_hold = "on_hold"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"

class TicketPriority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"

class TicketChannel(str, Enum):
    email = "email"
    web = "web"
    chat = "chat"
    phone = "phone"
    manual = "manual"
    api = "api"

class ClientOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    domain: Optional[str] = None
    company_id: Optional[int] = None

class TicketCreate(BaseModel):
    summary: str
    status: TicketStatus = TicketStatus.new
    priority: TicketPriority = TicketPriority.normal
    channel: TicketChannel = TicketChannel.email
    client_id: Optional[int] = None
    department_id: Optional[int] = None
    category_id: Optional[int] = None
    email_body: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None

class TicketPatch(BaseModel):
    summary: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    channel: Optional[TicketChannel] = None
    client_id: Optional[int] = None
    department_id: Optional[int] = None
    category_id: Optional[int] = None
    email_body: Optional[str] = None

class TicketOut(BaseModel):
    id: int
    ticket_id: str
    status: TicketStatus
    priority: TicketPriority
    channel: TicketChannel
    summary: str
    client_id: Optional[int] = None

class TicketWithClientFlat(BaseModel):
    id: int
    ticket_id: str
    status: TicketStatus
    priority: TicketPriority
    channel: TicketChannel
    summary: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_domain: Optional[str] = None
    company_name: Optional[str] = None

class StatusHistoryRow(BaseModel):
    id: int
    ticket_id: str
    from_status: Optional[TicketStatus] = None
    to_status: TicketStatus
    changed_at: str

class PriorityHistoryRow(BaseModel):
    id: int
    ticket_id: str
    from_priority: Optional[TicketPriority]
    to_priority: TicketPriority
    changed_at: str

class TicketFormattedOut(BaseModel):
    id: int
    ticket_id: str
    status: TicketStatus
    priority: TicketPriority
    channel: TicketChannel
    summary: str
    subject: Optional[str] = None
    body: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_email: Optional[str] = None
    department_name: Optional[str] = None
    category_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TicketsPage(BaseModel):
    data: List[TicketFormattedOut]
    count: Optional[int] = None
    limit: int
    offset: int
    next_offset: Optional[int] = None



class TicketsPageFormatted(BaseModel): 
    data: List[TicketFormattedOut]
    count: Optional[int] 
    limit: int
    offset: int
    next_offset: Optional[int]
