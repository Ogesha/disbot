import config
from database import Database

dsn = f"postgresql://{config.PG_USER}:{config.PG_PASSWORD}@{config.PG_HOST}:{config.PG_PORT}/{config.PG_DATABASE}"
db = Database(dsn)