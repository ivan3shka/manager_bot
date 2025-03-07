from peewee import (
    CharField,
    IntegerField,
    Model,
    SqliteDatabase,
    AutoField,
)

from config import DB_PATH

db = SqliteDatabase(DB_PATH)


class BaseModel(Model):
    class Meta:
        database = db


class UserManager(BaseModel):
    user_id = AutoField(primary_key=True)
    user_name = CharField()


class UserWorker(BaseModel):
    user_id = AutoField(primary_key=True)
    user_name = CharField()


class Task(BaseModel):
    task_id = AutoField(primary_key=True)
    task_name = CharField()
    id_worker = IntegerField()
    id_manager = IntegerField()
    date_start = CharField()
    date_finish = CharField()
    status = CharField()
    """
    Статус может быть: 
    process: Значит что задание создаётся
    work: Находится у worker
    finishing: worker выбрал для сдачи
    finish: Задание завершено 
    """


def create_models():
    db.create_tables(BaseModel.__subclasses__())
