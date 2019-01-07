from marshmallow import Schema, fields


class PublishJSONSchema(Schema):
    """Schema for Publish."""

    id = fields.String(required=True)
    data = fields.Dict(required=True)
    ai_service = fields.String()
