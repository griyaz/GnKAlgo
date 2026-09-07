from sqlalchemy.ext.declarative import declarative_base

# Central Base for SQLAlchemy models in the project.
# If your repo already has a Base model, replace imports to reuse it instead of this file.
Base = declarative_base()
