from contextlib import contextmanager

import peewee as pw
import playhouse.shortcuts


class BaseModel(pw.Model):
    class Meta:
        model_metadata_class = playhouse.shortcuts.ThreadSafeDatabaseMetadata


class Tag(BaseModel):
    tag_name = pw.CharField(null=False)
    project_id = pw.CharField(null=False)

    class Meta:
        indexes = ((("tag_name", "project_id"), True),)


class Result(BaseModel):
    client_id = pw.CharField(null=False)
    object_id = pw.UUIDField(null=False)
    filename = pw.CharField(null=False)

    class Meta:
        indexes = ((("client_id", "object_id"), True),)


class TaggedResult(BaseModel):
    tag = pw.ForeignKeyField(Tag, null=False)
    result = pw.ForeignKeyField(Result, null=False)


@contextmanager
def bind_to(db: pw.Database):
    with db.bind_ctx([Tag, Result, TaggedResult]):
        # create tables if they do not exist yet
        db.create_tables([Tag, Result, TaggedResult])
        yield
