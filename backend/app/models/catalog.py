"""Static control catalog reference data.

docs/baseline/D3-Control-Catalog.md section 2: the ENTIRE catalog is
flagged UNVERIFIED pending review by a GRC/compliance owner against
licensed ISO/NIST text. `Control.verification_status` defaults to
'Unverified' and nothing in this codebase ever writes 'Verified' to it --
that is a manual, human, out-of-band action this phase does not expose
an endpoint for (there is deliberately no API route that sets it).
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScreeningType(str, enum.Enum):
    MANDATORY = "Mandatory"
    CONDITIONAL = "Conditional"
    NOT_QUESTIONNAIRE = "NotQuestionnaire"


class Framework(str, enum.Enum):
    ISO27001_2022 = "ISO27001_2022"
    NIST_SP_800_53_R5 = "NIST_SP_800_53_R5"


class ControlSubject(str, enum.Enum):
    ORG = "Org"
    TARGET = "Target"
    TEST_ENV = "TestEnv"
    PLATFORM = "Platform"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "Unverified"
    VERIFIED = "Verified"


class ControlDomain(Base):
    __tablename__ = "control_domain"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # '1'..'11', '7a', '7b'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    screening: Mapped[ScreeningType] = mapped_column(Enum(ScreeningType), nullable=False)
    sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class Control(Base):
    __tablename__ = "control"

    control_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. 'A.8.31', 'SC-7'
    framework: Mapped[Framework] = mapped_column(Enum(Framework), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    domain_id: Mapped[str] = mapped_column(String(8), ForeignKey("control_domain.id"), nullable=False)
    subject: Mapped[ControlSubject] = mapped_column(Enum(ControlSubject), nullable=False)
    # Free-text status note from D3-Catalog (e.g. "Conditional - scope-triggered").
    # No enum here collapses this into a closed taxonomy -- the TASD-v1.0.md
    # compliance review (architecture/TASD-COMPLIANCE-REPORT.md, Finding M-02)
    # flagged exactly this collapse as an architectural interpretation to
    # confirm during catalog validation, so this phase keeps the baseline's
    # own free text verbatim instead of inventing a taxonomy.
    status_note: Mapped[str] = mapped_column(String(500), nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), nullable=False, default=VerificationStatus.UNVERIFIED
    )
