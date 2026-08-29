import os
from motor.motor_asyncio import AsyncIOMotorClient

_client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        mongo_url = os.environ["MONGO_URL"]
        _client = AsyncIOMotorClient(mongo_url)
        _db = _client[os.environ["DB_NAME"]]
    return _db


async def create_indexes():
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.missions.create_index("organization_id")
    await db.vendors.create_index([("mission_id", 1), ("domain", 1)])
    await db.offers.create_index("mission_id")
    await db.negotiations.create_index("mission_id")
    await db.agent_actions.create_index([("mission_id", 1), ("created_at", -1)])
    await db.memberships.create_index([("user_id", 1), ("organization_id", 1)])
