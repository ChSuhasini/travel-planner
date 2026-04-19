from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from app.db import Base

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False)
    days = Column(Integer, nullable=False)
    pace = Column(String, nullable=False)
    budget_nzd = Column(Integer, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)