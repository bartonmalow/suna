# Export router and initialize from the routes module
from .routes import router

# For now, create a simple initialize function
# TODO: Implement proper initialization logic if needed
def initialize(db_connection=None):
    """Initialize the versioning API"""
    from utils.logger import logger
    logger.info("Versioning API (routes) initialized")
    return router