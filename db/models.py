"""SQLAlchemy ORM models for the vitals streaming platform."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[str] = mapped_column(String(10), nullable=False)
    sex: Mapped[str] = mapped_column(
        String(1),
        CheckConstraint("sex IN ('M', 'F')", name="ck_patients_sex"),
        nullable=False,
    )
    room: Mapped[str] = mapped_column(String(10), nullable=False)
    primary_diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    admission_date: Mapped[str] = mapped_column(String(10), nullable=False)
    device_id: Mapped[str] = mapped_column(String(20), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=func.datetime("now")
    )


class VitalsReading(Base):
    __tablename__ = "vitals_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[str] = mapped_column(String(40), nullable=False)
    heart_rate: Mapped[float] = mapped_column(Float, nullable=False)
    systolic_bp: Mapped[float] = mapped_column(Float, nullable=False)
    diastolic_bp: Mapped[float] = mapped_column(Float, nullable=False)
    spo2: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    respiratory_rate: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly: Mapped[str | None] = mapped_column(String(50), nullable=True)
    device_id: Mapped[str] = mapped_column(String(20), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        Index("idx_vitals_patient_ts", "patient_id", timestamp.desc()),
    )
