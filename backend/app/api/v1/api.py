from fastapi import APIRouter

from app.api.v1.routes import bill, group, me, person, questionnaire, taxonomy

api_router = APIRouter()
api_router.include_router(me.router, tags=["me"])
api_router.include_router(group.router, tags=["group"])
api_router.include_router(person.router, tags=["person"])
api_router.include_router(questionnaire.router, tags=["questionnaire"])
api_router.include_router(bill.router, tags=["bill"])
api_router.include_router(taxonomy.router, tags=["taxonomy"])
