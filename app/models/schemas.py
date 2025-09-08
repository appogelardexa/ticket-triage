from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr

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


# -----------------
# Auth Schemas
# -----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: EmailStr
    redirect_to: Optional[str] = None

class ClientOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    domain: Optional[str] = None
    company_id: Optional[int] = None
    profile_image_link: Optional[str] = None

class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    domain: Optional[str] = None
    company_id: Optional[int] = None
    # Optional direct URL if already uploaded elsewhere
    profile_image_link: Optional[str] = None

class ClientPatch(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    domain: Optional[str] = None
    company_id: Optional[int] = None
    profile_image_link: Optional[str] = None

class TicketCreateInputV1(BaseModel):
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

class TicketCreateInputV2(BaseModel):
    summary: str
    status: Optional[TicketStatus] = TicketStatus.new
    priority: Optional[TicketPriority] = TicketPriority.P3
    channel: Optional[TicketChannel] = TicketChannel.email

    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None

    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    assignee_email: Optional[str] = None

    department_id: Optional[int] = None
    department_name: Optional[str] = None

    category_id: Optional[int] = None
    category_name: Optional[str] = None

    body: Optional[str] = None
    subject: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None


class TicketCreateInputV3(BaseModel):
    summary: str
    status: Optional[TicketStatus] = TicketStatus.new
    priority: Optional[TicketPriority] = TicketPriority.P3
    channel: Optional[TicketChannel] = TicketChannel.email

    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None

    assignee_id: Optional[int] = None
    department_id: Optional[int] = None
    category_id: Optional[int] = None

    body: Optional[str] = None
    subject: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None

class TicketCreatePublic(BaseModel):
    summary: str
    status: Optional[TicketStatus] = TicketStatus.new
    priority: Optional[TicketPriority] = TicketPriority.P3
    channel: Optional[TicketChannel] = TicketChannel.email

    client_name: Optional[str] = None
    client_email: Optional[str] = None

    assignee_name: Optional[str] = None
    assignee_email: Optional[str] = None

    department_name: Optional[str] = None
    category_name: Optional[str] = None

    body: Optional[str] = None
    subject: Optional[str] = None
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
    body: Optional[str] = None

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
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TicketsPage(BaseModel):
    data: List[TicketFormattedOut]
    count: Optional[int] = None
    limit: int
    offset: int
    next_offset: Optional[int] = None

class TicketsPageFormatted(BaseModel): 
    count: Optional[int] 
    limit: int
    offset: int
    next_offset: Optional[int]
    data: List[TicketFormattedOut]

class TicketsListWithCount(BaseModel):
    count: Optional[int] = None
    limit: int
    data: List[TicketFormattedOut]

# Departments
class DepartmentOut(BaseModel):
    id: int
    name: str
    google_channel: Optional[str] = None
    default_assignee_id: Optional[int] = None

class DepartmentCreate(BaseModel):
    name: str
    google_channel: Optional[str] = None
    default_assignee_id: Optional[int] = None
    
class DepartmentPatch(BaseModel):
    name: Optional[str] = None
    google_channel: Optional[str] = None
    default_assignee_id: Optional[int] = None

# Categories
class CategoryOut(BaseModel):
    id: int
    name: str
    description: str
    department_id: int
    default_slack_channel: Optional[str] = None
    auto_assign_to_id: Optional[int] = None

class CategoryCreate(BaseModel):
    name: str
    description: str
    department_id: int
    default_slack_channel: Optional[str] = None
    auto_assign_to_id: Optional[int] = None

class CategoryPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[int] = None
    default_slack_channel: Optional[str] = None
    auto_assign_to_id: Optional[int] = None

# Category Default Assignees
class CategoryDefaultAssigneeOut(BaseModel):
    id: int
    category_id: int
    staff_id: int
    priority: int = 100
    weight: int = 1
    is_fallback: bool = False
    active: bool = True
    created_at: Optional[datetime] = None

class CategoryDefaultAssigneeCreate(BaseModel):
    staff_id: int
    priority: int = 100
    weight: int = 1
    is_fallback: bool = False
    active: bool = True

class CategoryDefaultAssigneePatch(BaseModel):
    priority: Optional[int] = None
    weight: Optional[int] = None
    is_fallback: Optional[bool] = None
    active: Optional[bool] = None

class CategoryWithDefaultAssigneesOut(CategoryOut):
    default_assignees: List[CategoryDefaultAssigneeOut] = []

# ---------------------------------
# Ticket Attachments (metadata only)
# ---------------------------------
class TicketAttachmentOut(BaseModel):
    id: int
    ticket_id: int
    file_path: str
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    file_url: Optional[str] = None
    created_at: Optional[datetime] = None


class TicketCreatedWithAttachmentsOut(BaseModel):
    ticket: TicketFormattedOut
    attachments: List[TicketAttachmentOut] = []


# Variants that include attachments inline with tickets
class TicketFormattedWithAttachmentsOut(TicketFormattedOut):
    attachments: List[TicketAttachmentOut] = []


class TicketsPageFormattedWithAttachments(BaseModel):
    count: Optional[int]
    limit: int
    offset: int
    next_offset: Optional[int]
    data: List[TicketFormattedWithAttachmentsOut]


class TicketsListWithCountWithAttachments(BaseModel):
    count: Optional[int] = None
    limit: int
    data: List[TicketFormattedWithAttachmentsOut]


# -----------------
# Ticket Comments
# -----------------
class TicketCommentOut(BaseModel):
    id: int
    ticket_id: int  # FK to tickets.id
    internal_staff_id: int
    body: str
    is_private: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TicketCommentCreate(BaseModel):
    internal_staff_id: int
    body: str
    is_private: Optional[bool] = False


class TicketCommentPatch(BaseModel):
    body: Optional[str] = None
    is_private: Optional[bool] = None
