from sqlalchemy import BigInteger, Boolean, Column, JSON, Text, TIMESTAMP
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()
Base.__table_args__ = {"schema": "jira"}


class Epic(Base):
    __tablename__ = "epic"

    acc_id = Column(BigInteger, primary_key=True)
    id = Column(Text, primary_key=True)
    key = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    done = Column(Boolean, nullable=False)


class Issue(Base):
    __tablename__ = "issue"

    acc_id = Column(BigInteger, primary_key=True)
    id = Column(Text, primary_key=True)
    project_id = Column(Text, nullable=False)
    parent_id = Column(Text)
    key = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    status = Column(Text)
    labels = Column(postgresql.ARRAY(Text).with_variant(JSON(), sqlite.dialect.name))
    components = Column(postgresql.ARRAY(Text).with_variant(JSON(), sqlite.dialect.name))
    epic_id = Column(Text)
    created = Column(TIMESTAMP(timezone=True), nullable=False)
    updated = Column(TIMESTAMP(timezone=True), nullable=False)
    resolved = Column(TIMESTAMP(timezone=True))
    reporter_id = Column(Text, nullable=False)
    reporter_display_name = Column(Text, nullable=False)
    assignee_id = Column(Text)
    assignee_display_name = Column(Text)
    commenters_ids = Column(
        postgresql.ARRAY(BigInteger).with_variant(JSON(), sqlite.dialect.name))
    commenters_display_names = Column(
        postgresql.ARRAY(Text).with_variant(JSON(), sqlite.dialect.name))
    priority_id = Column(Text)  # TODO(vmarkovtsev): make it nullable=False
    priority_name = Column(Text, nullable=False)


class Component(Base):
    __tablename__ = "component"

    acc_id = Column(BigInteger, primary_key=True)
    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)


class User(Base):
    __tablename__ = "user"

    acc_id = Column(BigInteger, primary_key=True)
    id = Column(Text, primary_key=True)
    type = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    avatar_url = Column(Text, nullable=False)
