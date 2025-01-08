import peewee as pw
import playhouse.shortcuts

# defer initialization of database
db = pw.PostgresqlDatabase(None)


class BaseModel(pw.Model):
    class Meta:
        model_metadata_class = playhouse.shortcuts.ThreadSafeDatabaseMetadata


class Tag(BaseModel):
    tag_name = pw.CharField(null=False)
    project_id = pw.IntegerField(null=False)


class Result(BaseModel):
    client_id = pw.CharField(null=False)
    object_id = pw.UUIDField(null=False)
    filename = pw.CharField(null=False)

    class Meta:
        indexes = ((("client_id", "object_id"), True),)


class TaggedResult(BaseModel):
    tag = pw.ForeignKeyField(Tag, null=False)
    result = pw.ForeignKeyField(Result, null=False)
