from marshmallow import Schema, fields


class PublishJSONSchema(Schema):
    """Schema for Publish."""

    id = fields.String(required=True)
    data = fields.Raw(required=True)
    ai_service = fields.String()
