"""Product Utilities Shared Lambda Layer.

Contains shared business logic, validation, DynamoDB access, and response formatting:
- product_validator: Pydantic request models and data validation
- database_helper: DynamoDB table CRUD, query, and audit helpers
- response_formatter: Standardized API Gateway responses and error envelopes
"""
